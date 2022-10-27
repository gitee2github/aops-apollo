#!/usr/bin/python3  pylint:disable=too-many-lines
# ******************************************************************************
# Copyright (c) Huawei Technologies Co., Ltd. 2021-2021. All rights reserved.
# licensed under the Mulan PSL v2.
# You can use this software according to the terms and conditions of the Mulan PSL v2.
# You may obtain a copy of Mulan PSL v2 at:
#     http://license.coscl.org.cn/MulanPSL2
# THIS SOFTWARE IS PROVIDED ON AN 'AS IS' BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY OR FIT FOR A PARTICULAR
# PURPOSE.
# See the Mulan PSL v2 for more details.
# ******************************************************************************/
"""
Time:
Author:
Description: Host table operation
"""
from time import sleep
from collections import defaultdict
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import func, tuple_
from elasticsearch import ElasticsearchException

from vulcanus.log.log import LOGGER
from vulcanus.database.helper import sort_and_page, judge_return_code
from vulcanus.database.proxy import MysqlProxy, ElasticsearchProxy
from vulcanus.restful.status import DATABASE_INSERT_ERROR, DATABASE_QUERY_ERROR, NO_DATA, \
    SUCCEED, DATABASE_UPDATE_ERROR
from vulcanus.database.table import Host
from apollo.database.table import Cve, CveHostAssociation, CveUserAssociation, CveAffectedPkgs
from apollo.database.mapping import CVE_PKG_INDEX
from apollo.function.customize_exception import EsOperationError


class CveMysqlProxy(MysqlProxy):
    """
    Cve mysql related table operation
    """

    def get_cve_overview(self, data):
        """
        Get cve number overview based on severity

        Args:
            data(dict): parameter, e.g.
                {
                    "username": "admin",
                }

        Returns:
            int: status code
            dict: query result. e.g.
                {
                    "result": {
                        "Critical": 11,
                        "High": 6,
                        "Medium": 5,
                        "Low": 0,
                        "Unknown": 0
                    }
                }

        """
        result = {}
        try:
            result = self._get_processed_cve_overview(data)
            LOGGER.debug("Finished getting cve overview.")
            return SUCCEED, result
        except SQLAlchemyError as error:
            LOGGER.error(error)
            LOGGER.error("Getting cve overview failed due to internal error.")
            return DATABASE_QUERY_ERROR, result

    def _get_processed_cve_overview(self, data):
        """
        get cve overview info from database
        Args:
            data (dict): e.g. {"username": "admin"}

        Returns:
            dict
        """
        result = {
            "Critical": 0,
            "High": 0,
            "Medium": 0,
            "Low": 0,
            "Unknown": 0
        }
        username = data["username"]
        cve_overview_query = self._query_cve_overview(username)

        for severity, count in cve_overview_query:
            if severity not in result:
                LOGGER.debug("Unknown cve severity '%s' when getting overview." % severity)
                continue
            result[severity] = count
        return {"result": result}

    def _query_cve_overview(self, username):
        """
        query cve overview
        Args:
            username (str): user name of the request

        Returns:
            sqlalchemy.orm.query.Query
        """
        cve_overview_query = self.session.query(Cve.severity, func.count(Cve.cve_id)) \
            .join(CveUserAssociation, Cve.cve_id == CveUserAssociation.cve_id) \
            .filter(CveUserAssociation.username == username) \
            .group_by(Cve.severity)

        return cve_overview_query

    def get_cve_host(self, data):
        """
        Get hosts info of a cve

        Args:
            data(dict): parameter, e.g.
                {
                    "cve_id": "cve-2021-11111",
                    "sort": "last_scan",
                    "direction": "asc",
                    "page": 1,
                    "per_page": 10,
                    "username": "admin",
                    "filter": {
                        "host_name": "",
                        "host_group": ["group1"],
                        "repo": ["20.03-update"]
                    }
                }

        Returns:
            int: status code
            dict: query result. e.g.
                {
                    "total_count": 1,
                    "total_page": 1,
                    "result": [
                        {
                            "host_id": "id1",
                            "host_name": "name1",
                            "host_ip": "1.1.1.1",
                            "host_group": "group1",
                            "repo": "20.03-update",
                            "last_scan": 1111111111
                        }
                    ]
                }
        """
        result = {}
        try:
            status_code, result = self._get_processed_cve_hosts(data)
            LOGGER.debug("Finished getting cve hosts.")
            return status_code, result
        except SQLAlchemyError as error:
            LOGGER.error(error)
            LOGGER.error("Getting cve hosts failed due to internal error")
            return DATABASE_QUERY_ERROR, result

    def _get_processed_cve_hosts(self, data):
        """
        Query and process cve hosts data
        Args:
            data (dict): query condition

        Returns:
            int: status code
            dict
        """
        result = {
            "total_count": 0,
            "total_page": 1,
            "result": []
        }

        cve_id = data["cve_id"]
        filters = self._get_cve_hosts_filters(data.get("filter"))
        cve_hosts_query = self._query_cve_hosts(data["username"], cve_id, filters)

        total_count = len(cve_hosts_query.all())
        if not total_count:
            LOGGER.debug("No data found when getting the hosts of cve: %s." % cve_id)
            return SUCCEED, result

        sort_column = getattr(Host, data['sort']) if "sort" in data else None
        direction, page, per_page = data.get('direction'), data.get('page'), data.get('per_page')

        processed_query, total_page = sort_and_page(cve_hosts_query, sort_column,
                                                    direction, per_page, page)
        result['result'] = self._cve_hosts_row2dict(processed_query)
        result['total_page'] = total_page
        result['total_count'] = total_count

        return SUCCEED, result

    @staticmethod
    def _get_cve_hosts_filters(filter_dict):
        """
        Generate filters to filter cve hosts

        Args:
            filter_dict(dict): filter dict to filter cve hosts, e.g.
                {
                    "host_name": "",
                    "host_group": ["group1"],
                    "repo": ["20.03-update"]
                }

        Returns:
            set
        """
        filters = set()
        if not filter_dict:
            return filters

        if filter_dict.get("host_name"):
            filters.add(Host.host_id.like("%" + filter_dict["host_name"] + "%"))
        if filter_dict.get("host_group"):
            filters.add(Host.host_group_name.in_(filter_dict["host_group"]))
        if filter_dict.get("repo"):
            filters.add(Host.repo_name.in_(filter_dict["repo"]))

        return filters

    def _query_cve_hosts(self, username, cve_id, filters):
        """
        query needed cve hosts info
        Args:
            username (str): user name of the request
            cve_id (str): cve id
            filters (set): filter given by user

        Returns:
            sqlalchemy.orm.query.Query
        """
        cve_query = self.session.query(Host.host_id, Host.host_name, Host.public_ip,
                                       Host.host_group_name, Host.repo_name, Host.last_scan) \
            .join(CveHostAssociation, Host.host_id == CveHostAssociation.host_id) \
            .filter(Host.user == username, CveHostAssociation.cve_id == cve_id) \
            .filter(*filters)

        return cve_query

    @staticmethod
    def _cve_hosts_row2dict(rows):
        result = []
        for row in rows:
            host_info = {
                "host_id": row.host_id,
                "host_name": row.host_name,
                "host_ip": row.public_ip,
                "host_group": row.host_group_name,
                "repo": row.repo_name,
                "last_scan": row.last_scan,
            }
            result.append(host_info)
        return result

    def get_cve_task_hosts(self, data):
        """
        get hosts basic info of multiple CVE
        Args:
            data (dict): parameter, e.g.
                {
                    "cve_list": ["cve-2021-11111", "cve-2021-11112"],
                    "username": "admin"
                }

        Returns:
            int: status code
            dict: query result. e.g.
                {
                    "result": {
                        "cve-2021-11111": [
                            {
                                "host_id": "id1",
                                "host_name": "name1",
                                "host_ip": "1.1.1.1"
                            },
                            {
                                "host_id": "id2",
                                "host_name": "name2",
                                "host_ip": "1.1.1.2"
                            }
                        ],
                        "cve-2021-11112": [
                            {
                                "host_id": "id1",
                                "host_name": "name1",
                                "host_ip": "1.1.1.1"
                            }
                        ]
                    }
                }
        """
        result = {}
        try:
            status_code, result = self._get_processed_cve_task_hosts(data)
            LOGGER.debug("Finished querying cve task hosts.")
            return status_code, result
        except SQLAlchemyError as error:
            LOGGER.error(error)
            LOGGER.error("Getting cve task hosts failed due to internal error.")
            return DATABASE_QUERY_ERROR, result

    def _get_processed_cve_task_hosts(self, data):
        """
        Query and process cve task hosts data
        Args:
            data (dict): query condition

        Returns:
            int: status code
            dict
        """
        cve_list = data["cve_list"]
        username = data["username"]
        cve_task_hosts = self._query_cve_task_hosts(username, cve_list)

        result = defaultdict(list)
        for row in cve_task_hosts:
            host_dict = self._cve_task_hosts_row2dict(row)
            result[row.cve_id].append(host_dict)

        succeed_list = list(result.keys())
        fail_list = list(set(cve_list) - set(succeed_list))

        if fail_list:
            LOGGER.debug("No data found when getting the task hosts of cve: %s." % fail_list)

        status_dict = {"succeed_list": succeed_list, "fail_list": fail_list}
        status_code = judge_return_code(status_dict, NO_DATA)
        return status_code, {"result": dict(result)}

    def _query_cve_task_hosts(self, username, cve_list):
        """
        query needed cve hosts basic info
        Args:
            username (str): user name of the request
            cve_list (list): cve id list

        Returns:
            sqlalchemy.orm.query.Query
        """
        cve_query = self.session.query(CveHostAssociation.cve_id, Host.host_id,
                                       Host.host_name, Host.public_ip) \
            .join(CveHostAssociation, Host.host_id == CveHostAssociation.host_id) \
            .filter(Host.user == username, CveHostAssociation.cve_id.in_(cve_list))
        return cve_query

    @staticmethod
    def _cve_task_hosts_row2dict(row):
        host_info = {
            "host_id": row.host_id,
            "host_name": row.host_name,
            "host_ip": row.public_ip
        }
        return host_info

    def set_cve_status(self, data):
        """
        Set cve status
        Notice, if a cve id doesn't exist, all cve will not be updated
        Args:
            data (dict): parameter, e.g.
                {
                    "cve_list": ["cve-2021-11111", "cve-2021-11112"],
                    "status": "on-hold",
                    "username": "admin"
                }

        Returns:
            int: status code
        """
        try:
            status_code = self._update_cve_status(data)
            self.session.commit()
            LOGGER.debug("Finished updating cve status.")
            return status_code
        except SQLAlchemyError as error:
            self.session.rollback()
            LOGGER.error(error)
            LOGGER.error("Updating cve status failed due to internal error")
            return DATABASE_UPDATE_ERROR

    def _update_cve_status(self, data):
        """
        Update cve status.
        Args:
            data (dict): parameter, e.g.
                {
                    "cve_list": ["xxx-xxxx-xxxx", "xxx-xxxx-xxx"],
                    "status": "on-hold",
                    "username": "admin"
                }

        Returns:
            int
        """
        cve_list = data["cve_list"]
        status = data["status"]
        username = data["username"]

        cve_status_query = self._query_cve_status(username, cve_list)
        succeed_list = [row.cve_id for row in cve_status_query]
        fail_list = list(set(cve_list) - set(succeed_list))
        if fail_list:
            LOGGER.debug("No data found when setting the status of cve: %s." % fail_list)
            return NO_DATA

        # update() is not applicable to 'in_' method without synchronize_session=False
        cve_status_query.update({CveUserAssociation.status: status}, synchronize_session=False)
        return SUCCEED

    def _query_cve_status(self, username, cve_list):
        """
        query needed cve status of specific user
        Args:
            username (str): user name of the request
            cve_list (list): cve id list

        Returns:
            sqlalchemy.orm.query.Query
        """
        cve_query = self.session.query(CveUserAssociation) \
            .filter(CveUserAssociation.username == username,
                    CveUserAssociation.cve_id.in_(cve_list))
        return cve_query

    def get_cve_action(self, data):
        """
        query cve action
        Args:
            data (dict): parameter, e.g.
                {
                    "cve_list": ["cve-2021-11111", "cve-2021-11112"]
                }

        Returns:
            int: status code
            dict: query result. e.g.
                {
                    "result": {
                        "cve-2021-11111": {
                            "reboot": True,
                            "package": "redis"
                        },
                        "cve-2021-11112": {
                            "reboot": False,
                            "package": "tensorflow"
                        },
                    }
                }
        """
        result = {}
        try:
            status_code, result = self._get_processed_cve_action(data)
            LOGGER.debug("Finished querying cve action.")
            return status_code, result
        except SQLAlchemyError as error:
            LOGGER.error(error)
            LOGGER.error("Getting cve action failed due to internal error.")
            return DATABASE_INSERT_ERROR, result

    def _get_processed_cve_action(self, data):
        """
        Query and process cve action data
        Args:
            data (dict): cve list info

        Returns:
            int: status code of operation
            dict
        """
        cve_list = data["cve_list"]
        result = {}

        cve_action_query = self._query_cve_action(cve_list)

        for row in cve_action_query:
            if row.cve_id not in result:
                result[row.cve_id] = {"reboot": row.reboot, "package": row.package}
            else:
                result[row.cve_id]["package"] += "," + row.package

        succeed_list = [row.cve_id for row in cve_action_query]
        fail_list = list(set(cve_list) - set(succeed_list))
        if fail_list:
            LOGGER.debug("No data found when getting the action of cve: %s." % fail_list)

        status_dict = {"succeed_list": succeed_list, "fail_list": fail_list}
        status_code = judge_return_code(status_dict, NO_DATA)
        return status_code, {"result": result}

    def _query_cve_action(self, cve_list):
        """
        query cve action info from database
        Args:
            cve_list (list): cve id list

        Returns:
            sqlalchemy.orm.query.Query

        """
        cve_action_query = self.session.query(Cve.cve_id, CveAffectedPkgs.package, Cve.reboot) \
            .join(CveAffectedPkgs) \
            .filter(Cve.cve_id.in_(cve_list))
        return cve_action_query


class CveEsProxy(ElasticsearchProxy):  # pylint:disable=too-few-public-methods
    """
    Cve elasticsearch database related operation
    """

    def _get_cve_description(self, cve_list):
        """
        description of the cve in list
        Args:
            cve_list (list): cve id list

        Returns:
            dict: cve description dict. e.g.
                {"cve_id1": "a long description"}
        Raises:
            EsOperationError
        """
        query_body = self._general_body()

        query_body['query']['bool']['must'].append(
            {"terms": {"cve_id": cve_list}})
        operation_code, res = self.query(CVE_PKG_INDEX, query_body,
                                         source=["cve_id", "description"])

        if not operation_code:
            raise EsOperationError("Query cve description in elasticsearch failed.")

        description_dict = {}
        for hit in res["hits"]["hits"]:
            cve_id = hit["_source"]["cve_id"]
            description_dict[cve_id] = hit["_source"]["description"]
        return description_dict


class CveProxy(CveMysqlProxy, CveEsProxy):
    """
    Cve related database operation
    """

    def __init__(self, configuration, host=None, port=None):
        """
        Instance initialization

        Args:
            configuration (Config)
            host(str)
            port(int)
        """
        CveMysqlProxy.__init__(self)
        CveEsProxy.__init__(self, configuration, host, port)

    def connect(self, session):
        """ connect database"""
        return CveMysqlProxy.connect(self, session) and ElasticsearchProxy.connect(self)

    def close(self):
        """ close connection """
        CveMysqlProxy.close(self)
        ElasticsearchProxy.close(self)

    def __del__(self):
        CveMysqlProxy.__del__(self)
        ElasticsearchProxy.__del__(self)

    def get_cve_list(self, data):
        """
        Get cve list of a user

        Args:
            data(dict): parameter, e.g.
                {
                    "sort": "cve_id",
                    "direction": "asc",
                    "page": 1,
                    "per_page": 10,
                    "username": "admin",
                    "filter": {
                        "cve_id": "cve-2021",
                        "severity": "medium",
                        "status": "in review"
                    }
                }

        Returns:
            int: status code
            dict: query result. e.g.
                {
                    "total_count": 1,
                    "total_page": 1,
                    "result": [
                        {
                            "cve_id": "cve-2021-11111",
                            "publish_time": "2020-03-22",
                            "severity": "medium",
                            "description": "a long description",
                            "cvss_score": "7.2",
                            "host_num": 22,
                            "status": "on hold"
                        }
                    ]
                }
        """
        result = {}
        try:
            result = self._get_processed_cve_list(data)
            LOGGER.debug("Finished getting cve list.")
            return SUCCEED, result
        except (SQLAlchemyError, ElasticsearchException, EsOperationError) as error:
            LOGGER.error(error)
            LOGGER.error("Getting cve list failed due to internal error.")
            return DATABASE_QUERY_ERROR, result

    def _get_processed_cve_list(self, data):
        """
        Get sorted, paged and filtered cve list.

        Args:
            data(dict): sort, page and filter info
        Returns:
            dict
        Raises:
            EsOperationError
        """
        result = {
            "total_count": 0,
            "total_page": 0,
            "result": []
        }

        filters = self._get_cve_list_filters(data.get("filter"))
        cve_query = self._query_cve_list(data["username"], filters)

        total_count = len(cve_query.all())
        if not total_count:
            return result

        sort_column = self._get_cve_list_sort_column(data.get('sort'))
        direction, page, per_page = data.get('direction'), data.get('page'), data.get('per_page')

        processed_query, total_page = sort_and_page(cve_query, sort_column,
                                                    direction, per_page, page)
        description_dict = self._get_cve_description([row.cve_id for row in processed_query])

        result['result'] = self._cve_list_row2dict(processed_query, description_dict)
        result['total_page'] = total_page
        result['total_count'] = total_count

        return result

    @staticmethod
    def _get_cve_list_sort_column(column_name):
        """
        get column or aggregation column of table by name
        Args:
            column_name (str/None): name of column

        Returns:
            column or aggregation column of table, or None if column name is not given
        """
        if not column_name:
            return None
        if column_name == "host_num":
            return func.count(CveHostAssociation.host_id)
        return getattr(Cve, column_name)

    def _query_cve_list(self, username, filters):
        """
        query needed cve info
        Args:
            username (str): user name of the request
            filters (set): filter given by user

        Returns:
            sqlalchemy.orm.query.Query
        """
        cve_query = self.session.query(Cve.cve_id, Cve.publish_time, Cve.severity,
                                       Cve.cvss_score, CveUserAssociation.status,
                                       func.count(CveHostAssociation.host_id).label("host_num")) \
            .join(CveHostAssociation, Cve.cve_id == CveHostAssociation.cve_id) \
            .join(CveUserAssociation) \
            .filter(CveUserAssociation.username == username) \
            .filter(*filters) \
            .group_by(Cve.cve_id)

        return cve_query

    @staticmethod
    def _cve_list_row2dict(rows, description_dict):
        """
        reformat queried rows to list of dict and add description for each cve
        Args:
            rows:
            description_dict (dict): key is cve's id, value is cve's description

        Returns:
            list
        """
        result = []
        for row in rows:
            cve_id = row.cve_id
            cve_info = {
                "cve_id": cve_id,
                "publish_time": row.publish_time,
                "severity": row.severity,
                "description": description_dict[cve_id] if description_dict.get(cve_id) else "",
                "cvss_score": row.cvss_score,
                "status": row.status,
                "host_num": row.host_num
            }
            result.append(cve_info)
        return result

    @staticmethod
    def _get_cve_list_filters(filter_dict):
        """
        Generate filters

        Args:
            filter_dict(dict): filter dict to filter cve list, e.g.
                {
                    "cve_id": "2021",
                    "severity": ["high"],
                    "status": ["in review", "not reviewed"]
                }

        Returns:
            set
        """
        filters = set()
        if not filter_dict:
            return filters

        if filter_dict.get("cve_id"):
            filters.add(Cve.cve_id.like("%" + filter_dict["cve_id"] + "%"))
        if filter_dict.get("severity"):
            filters.add(Cve.severity.in_(filter_dict["severity"]))
        if filter_dict.get("status"):
            filters.add(CveUserAssociation.status.in_(filter_dict["status"]))

        return filters

    def get_cve_info(self, data):
        """
        Get cve number overview based on severity

        Args:
            data(dict): parameter, e.g.
                {
                    "cve_id": "cve-2021-11111"
                    "username": "admin",
                }

        Returns:
            int: status code
            dict: query result. e.g.
                {
                    "result": {
                        "cve_id": "cve-2021-11111",
                        "publish_time": "2020-09-24",
                        "severity": "high",
                        "description": "a long description",
                        "cvss_score": "7.2",
                        "status": "in review",
                        "package": "tensorflow,redis",
                        "related_cve": [
                            "cve-2021-11112", "cve-2021-11113"
                        ]
                    }
                }
        """
        result = {}
        try:
            status_code, result = self._get_processed_cve_info(data)
            LOGGER.debug("Finished getting cve info.")
            return status_code, result
        except (SQLAlchemyError, ElasticsearchException, EsOperationError) as error:
            LOGGER.error(error)
            LOGGER.error("Getting cve info failed due to internal error.")
            return DATABASE_QUERY_ERROR, result

    def _get_processed_cve_info(self, data):
        """
        query and process cve info
        Args:
            data (dict): {"cve_id": "cve-2021-11111", "username": "admin"}

        Returns:
            int: status code
            dict: query result

        Raises:
            sqlalchemy.orm.exc.MultipleResultsFound
            EsOperationError
        """
        cve_id = data["cve_id"]
        username = data["username"]

        cve_info_query = self._query_cve_info(username, cve_id)
        if not cve_info_query.all():
            LOGGER.debug("No data found when getting the info of cve: %s." % cve_id)
            return NO_DATA, {"result": {}}

        # raise exception when multiple record found
        cve_info_data = cve_info_query.one()
        description_dict = self._get_cve_description([cve_info_data.cve_id])
        pkg_list = self._get_affected_pkgs(cve_id)

        info_dict = self._cve_info_row2dict(cve_info_data, description_dict, pkg_list)
        info_dict["related_cve"] = self._get_related_cve(username, cve_id, pkg_list)
        return SUCCEED, {"result": info_dict}

    def _query_cve_info(self, username, cve_id):
        """
        query needed cve info
        Args:
            username (str): user name of the request
            cve_id (str): cve id

        Returns:
            sqlalchemy.orm.query.Query
        """
        cve_info_query = self.session.query(Cve.cve_id, Cve.publish_time, Cve.severity,
                                            Cve.cvss_score, CveUserAssociation.status) \
            .join(CveUserAssociation) \
            .filter(Cve.cve_id == cve_id, CveUserAssociation.username == username)

        return cve_info_query

    def _get_affected_pkgs(self, cve_id):
        """
        get cve's affected packages
        Args:
            cve_id (str): cve id

        Returns:
            list
        """
        pkg_query = self.session.query(CveAffectedPkgs.package) \
            .filter(CveAffectedPkgs.cve_id == cve_id)
        pkg_list = [row.package for row in pkg_query]
        return pkg_list

    def _get_related_cve(self, username, cve_id, pkg_list):
        """
        get related CVEs which have same package as the given cve
        Args:
            username (str): username
            cve_id (str): cve id
            pkg_list (list): package name list of the given cve

        Returns:
            list
        """
        # if list is empty, which may happened when CVE's package is
        # not record, return empty list
        if not pkg_list:
            return []

        exist_cve_query = self.session.query(CveHostAssociation.cve_id) \
            .join(Host) \
            .filter(Host.user == username)
        # get first column value from tuple to list
        exist_cve_list = list(zip(*exist_cve_query))[0]

        related_cve_query = self.session.query(CveAffectedPkgs.cve_id) \
            .filter(CveAffectedPkgs.package.in_(pkg_list)) \
            .filter(CveAffectedPkgs.cve_id.in_(exist_cve_list))
        related_cve = set(list(zip(*related_cve_query))[0])

        related_cve.remove(cve_id)
        return list(related_cve)

    @staticmethod
    def _cve_info_row2dict(row, description_dict, pkg_list):
        """
        reformat queried row to dict and add description for the cve
        Args:
            row:
            description_dict (dict): key is cve's id, value is cve's description
            pkg_list (list): cve's affected packages

        Returns:
            dict
        """
        cve_id = row.cve_id
        cve_info = {
            "cve_id": cve_id,
            "publish_time": row.publish_time,
            "severity": row.severity,
            "description": description_dict[cve_id] if description_dict.get(cve_id) else "",
            "cvss_score": row.cvss_score,
            "status": row.status,
            "package": ','.join(pkg_list),
            "related_cve": []
        }
        return cve_info

    def save_security_advisory(self, file_name, cve_rows, cve_pkg_rows, cve_pkg_docs):
        """
        save security advisory to mysql and es
        Args:
            file_name (str): security advisory's name
            cve_rows (list): list of dict to insert to mysql Cve table
            cve_pkg_rows (list): list of dict to insert to mysql CveAffectedPkgs table
            cve_pkg_docs (list): list of dict to insert to es CVE_PKG_INDEX

        Returns:
            int: status code
        """
        try:
            self._save_security_advisory(cve_rows, cve_pkg_rows, cve_pkg_docs)
            self.session.commit()
            LOGGER.debug("Finished saving security advisory '%s'." % file_name)
            return SUCCEED
        except (SQLAlchemyError, ElasticsearchException, EsOperationError) as error:
            self.session.rollback()
            LOGGER.error(error)
            LOGGER.error("Saving security advisory '%s' failed due to internal error." % file_name)
            return DATABASE_INSERT_ERROR

    def _save_security_advisory(self, cve_rows, cve_pkg_rows, cve_pkg_docs):
        """
        save data into mysql and es

        Args:
            cve_rows (list): list of dict to insert to mysql Cve table
            cve_pkg_rows (list): list of dict to insert to mysql CveAffectedPkgs table
            cve_pkg_docs (list): list of dict to insert to es CVE_PKG_INDEX

        Raises:
            SQLAlchemyError, ElasticsearchException, EsOperationError
        """
        cve_list = [row_dict["cve_id"] for row_dict in cve_rows]
        cve_query = self.session.query(Cve.cve_id).filter(Cve.cve_id.in_(cve_list))
        update_cve_set = {row.cve_id for row in cve_query}

        update_cve_rows = []
        insert_cve_rows = []
        for row in cve_rows:
            if row["cve_id"] in update_cve_set:
                update_cve_rows.append(row)
            else:
                insert_cve_rows.append(row)

        # Cve table need commit after add, otherwise following insertion will fail due to
        # Cve.cve_id foreign key constraint.
        # In some case the cve may already exist and some info may changed like cvss score,
        # here we choose insert + commit then update instead of session.merge(), so that when
        # rolling back due to some error, the updated info can be rolled back
        self.session.bulk_insert_mappings(Cve, insert_cve_rows)
        self.session.commit()
        try:
            self.session.bulk_update_mappings(Cve, update_cve_rows)
            self._insert_cve_pkg_rows(cve_pkg_rows)
            self._save_cve_pkg_docs(cve_pkg_docs)
        except (SQLAlchemyError, ElasticsearchException, EsOperationError):
            self.session.rollback()
            self._delete_cve_rows(insert_cve_rows)
            self.session.commit()
            raise

    def _insert_cve_pkg_rows(self, cve_pkg_rows):
        """
        insert rows into mysql CveAffectedPkgs table. Ignore the rows which already exist

        Args:
            cve_pkg_rows (list): list of row dict. e.g.
                [{"cve_id": "cve-2021-1001", "package": "redis"}]
        """
        # get the tuples of cve_id and package name
        cve_pkg_keys = [(row["cve_id"], row["package"]) for row in cve_pkg_rows]

        # delete the exist records first then insert the rows
        self.session.query(CveAffectedPkgs) \
            .filter(tuple_(CveAffectedPkgs.cve_id, CveAffectedPkgs.package)
                    .in_(cve_pkg_keys)) \
            .delete(synchronize_session=False)
        self.session.bulk_insert_mappings(CveAffectedPkgs, cve_pkg_rows)

    def _save_cve_pkg_docs(self, cve_pkg_docs):
        """
        insert docs into es CVE_PKG_INDEX, document id is cve's id
        if the cve already exist, add rpm package to specific arch's package list (if a package's
        version or release update, still add it to list directly)
        Args:
            cve_pkg_docs (list):
                [{'cve_id': 'CVE-2021-43809',
                  'description': 'a long description',
                  'os_list': [{'arch_list': [{'arch': 'noarch',
                                              'package': ['xxx-1.0.0-1.oe1.noarch.rpm',
                                                          'xxx-help-1.0.0-1.oe1.noarch.rpm']},
                                             {'arch': 'src',
                                              'package': ['xxx-1.0.0-1.oe1.src.rpm']}],
                               'os_version': 'openEuler:20.03-LTS-SP1',
                               'update_time': '2021-12-31'}]}]  // SP2 dict is omitted here
        Raises:
            EsOperationError
        """
        cve_list = [doc["cve_id"] for doc in cve_pkg_docs]
        exist_docs = self._get_exist_cve_pkg_docs(cve_list)
        exist_cve_set = {doc["cve_id"] for doc in exist_docs}
        update_docs = []
        insert_docs = []

        for doc in cve_pkg_docs:
            if doc["cve_id"] in exist_cve_set:
                update_docs.append(doc)
            else:
                insert_docs.append(doc)

        # elasticsearch need 1 second to update doc
        self._insert_cve_pkg_docs(insert_docs)
        try:
            self._update_cve_pkg_docs(exist_docs, update_docs)
            sleep(1)
        except EsOperationError:
            sleep(1)
            insert_cve_list = [doc["cve_id"] for doc in insert_docs]
            self._delete_cve_pkg_docs(insert_cve_list)
            raise

    def _get_exist_cve_pkg_docs(self, cve_list):
        """
        query exist cve package doc from elasticsearch
        Args:
            cve_list (list): cve id list

        Returns:
            list: list of cve's pkg info doc

        Raises:
            EsOperationError
        """
        query_body = self._general_body()
        query_body['query']['bool']['must'].append(
            {"terms": {"_id": cve_list}})
        operation_code, res = self.query(CVE_PKG_INDEX, query_body, source=True)

        if not operation_code:
            raise EsOperationError("Query exist cve in elasticsearch failed.")

        docs = [hit["_source"] for hit in res["hits"]["hits"]]
        return docs

    def _insert_cve_pkg_docs(self, cve_pkg_docs):
        """
        insert new cve info into es CVE_PKG_INDEX
        Args:
            cve_pkg_docs (list): list of doc dict

        Raises:
            EsOperationError
        """
        action = []
        for item in cve_pkg_docs:
            action.append({
                "_index": CVE_PKG_INDEX,
                "_source": item,
                "_id": item["cve_id"]})

        res = self._bulk(action)
        if not res:
            raise EsOperationError("Insert docs into elasticsearch failed.")

    def _update_cve_pkg_docs(self, exist_docs, update_docs):
        """
        update cve's package info in es CVE_PKG_INDEX
        Args:
            exist_docs (list): the doc already exist in es
            update_docs (list): the doc to be updated to es

        Raises:
            EsOperationError
        """

        def reformat_doc_list(doc_list):
            doc_dict = {}
            for doc in doc_list:
                doc_dict[doc["cve_id"]] = doc
            return doc_dict

        try:
            exist_docs_dict = reformat_doc_list(exist_docs)
            action = []
            for update_doc in update_docs:
                cve_id = update_doc["cve_id"]
                exist_doc = exist_docs_dict[cve_id]
                merged_doc = self._merge_cve_pkg_doc(exist_doc, update_doc)
                action.append({
                    "_id": cve_id,
                    "_source": merged_doc,
                    "_index": CVE_PKG_INDEX})
        except (KeyError, TypeError) as error:
            raise EsOperationError("Update docs into elasticsearch failed when process data, "
                                   "%s." % error) from error

        bulk_update_res = self._bulk(action)
        if not bulk_update_res:
            raise EsOperationError("Update docs into elasticsearch failed.")

    @staticmethod
    def _merge_cve_pkg_doc(old_doc, new_doc):
        """
        merge two doc together
        doc format:
        {'cve_id': 'CVE-2021-43809',
         'description': 'a long description',
         'os_list': [{'arch_list': [{'arch': 'noarch',
                                     'package': ['rubygem-bundler-2.2.33-1.oe1.noarch.rpm',
                                                 'rubygem-bundler-help-2.2.33-1.oe1.noarch.rpm']},
                                    {'arch': 'src',
                                     'package': ['rubygem-bundler-2.2.33-1.oe1.src.rpm']}],
                      'os_version': 'openEuler:20.03-LTS-SP1',
                      'update_time': '2021-12-31'}]}
        Args:
            old_doc (dict): exist doc
            new_doc (dict): update doc

        Returns:
            dict: merged doc
        """

        def reformat_os_list(os_list):
            os_dict = {}
            for os_info in os_list:
                os_dict[os_info["os_version"]] = os_info
            return os_dict

        def reformat_arch_list(arch_list):
            arch_dict = {}
            for arch_info in arch_list:
                arch_dict[arch_info["arch"]] = arch_info
            return arch_dict

        def merge_arch_list(old_os_data, new_os_data):
            old_arch_dict = reformat_arch_list(old_os_data["arch_list"])
            new_arch_list = new_os_data["arch_list"]
            for new_arch_info in new_arch_list:
                arch_name = new_arch_info["arch"]
                if arch_name in old_arch_dict:
                    old_arch_info = old_arch_dict.pop(arch_name)
                    pkgs_set = set(new_arch_info["package"]) | set(old_arch_info["package"])
                    new_arch_info["package"] = list(pkgs_set)
            for left_arch_info in old_arch_dict.values():
                new_arch_list.append(left_arch_info)

        old_os_dict = reformat_os_list(old_doc["os_list"])
        new_os_list = new_doc["os_list"]
        for new_os_info in new_os_list:
            os_version = new_os_info["os_version"]
            if os_version in old_os_dict:
                old_os_info = old_os_dict.pop(os_version)
                merge_arch_list(old_os_info, new_os_info)

        for left_os_info in old_os_dict.values():
            new_os_list.append(left_os_info)
        return new_doc

    def _delete_cve_pkg_docs(self, cve_list):
        """
        delete inserted docs to rollback
        Args:
            cve_list (list): the cve list to be delete

        Returns:

        """
        if not cve_list:
            return

        delete_body = self._general_body()
        delete_body["query"]["bool"]["must"].append(
            {"terms": {"_id": cve_list}})
        status = self.delete(CVE_PKG_INDEX, delete_body)
        if not status:
            LOGGER.error("Roll back advisory insertion in es failed due to es error, record of "
                         "cve '%s' remain in es." % cve_list)
            return
        LOGGER.debug("Roll back advisory insertion in es succeed.")

    def _delete_cve_rows(self, insert_cve_rows):
        """
        delete inserted cve table rows
        Args:
            insert_cve_rows (list): cve row dict list

        Returns:

        """
        insert_cve_list = [row["cve_id"] for row in insert_cve_rows]
        self.session.query(Cve).filter(Cve.cve_id.in_(insert_cve_list)) \
            .delete(synchronize_session=False)