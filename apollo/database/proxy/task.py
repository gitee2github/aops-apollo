#!/usr/bin/python3
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
Description: vulnerability related database operation
"""
from time import time
import math
import json
from collections import defaultdict
from sqlalchemy.exc import SQLAlchemyError
from elasticsearch import ElasticsearchException

from aops_utils.log.log import LOGGER
from aops_utils.database.helper import sort_and_page, judge_return_code
from aops_utils.database.proxy import MysqlProxy, ElasticsearchProxy
from aops_utils.restful.status import DATABASE_DELETE_ERROR, DATABASE_INSERT_ERROR, NO_DATA, \
    DATABASE_QUERY_ERROR, DATABASE_UPDATE_ERROR, SUCCEED, PARAM_ERROR, SERVER_ERROR, PARTIAL_SUCCEED
from aops_utils.database.table import Host, User
from apollo.database.table import Cve, Task, TaskCveHostAssociation, TaskHostRepoAssociation, \
    CveTaskAssociation, CveHostAssociation, CveAffectedPkgs, CveUserAssociation
from apollo.conf.constant import TASK_INDEX
from apollo.function.customize_exception import EsOperationError


task_types = ["cve", "repo"]


class TaskMysqlProxy(MysqlProxy):
    """
    Task related mysql table operation
    """

    def get_scan_host_info(self, username, host_list):
        """
        Query host info according to host id list.

        Args:
            username (str): user name
            host_list (list): host id list, can be empty

        Returns:
            list: host info, e.g.
                [
                    {
                        "host_id": "",
                        "host_ip": "",
                        "host_name": "",
                        "status": ""
                    }
                ]
        """
        result = []
        try:
            result = self._get_host_info(username, host_list)
            LOGGER.debug("Finished getting host info.")
            return result
        except SQLAlchemyError as error:
            LOGGER.error(error)
            LOGGER.error("Getting host info failed due to internal error.")
            return result

    def _get_host_info(self, username, host_list):
        """
        get info of the host id in host_list. If host list is empty, query all hosts
        """
        filters = {Host.user == username}
        if host_list:
            filters.add(Host.host_id.in_(host_list))

        info_query = self.session.query(Host.host_id, Host.host_name, Host.public_ip, Host.status) \
            .filter(*filters)

        info_list = []
        for row in info_query:
            host_info = {
                "host_id": row.host_id,
                "host_name": row.host_name,
                "host_ip": row.public_ip,
                "status": row.status
            }
            info_list.append(host_info)
        return info_list

    def get_total_host_info(self):
        """
        Get the whole host info of each user.
        Args:

        Returns:
            int: status code
            dict: query result
        """
        temp_res = {}
        result = {"host_infos": temp_res}

        try:
            users = self.session.query(User).all()
            for user in users:
                name = user.username
                temp_res[name] = []
                for host in user.hosts:
                    host_info = {
                        "host_id": host.host_id,
                        "host_name": host.host_name,
                        "host_ip": host.public_ip,
                        "status": host.status
                    }
                    temp_res[name].append(host_info)
            return SUCCEED, result
        except SQLAlchemyError as error:
            LOGGER.error(error)
            LOGGER.error("query host basic info fail")
            return DATABASE_QUERY_ERROR, result

    def init_host_scan(self, username, host_list):
        """
        When the host need to be scanned, init the status to 'scanning',
        and update the last scan time to current time.
        Notice, if one host id doesn't exist, all hosts will not be scanned
        Args:
            username (str): user name
            host_list (list): host id list, if empty, scan all hosts
        Returns:
            int: status code
        """
        try:
            status_code = self._update_host_scan("init", host_list, username)
            self.session.commit()
            LOGGER.debug("Finished init host scan status.")
            return status_code
        except SQLAlchemyError as error:
            self.session.rollback()
            LOGGER.error(error)
            LOGGER.error("Init host scan status failed due to internal error.")
            return DATABASE_UPDATE_ERROR

    def update_scan_status(self, host_list):
        """
        Every time a host or host list have been scanned, update the status to "done"

        Args:
            host_list (list): host id list

        Returns:
            int: status code
        """
        try:
            status_code = self._update_host_scan("finish", host_list)
            self.session.commit()
            LOGGER.debug("Finished updating host status after scanned.")
            return status_code
        except SQLAlchemyError as error:
            self.session.rollback()
            LOGGER.error(error)
            LOGGER.error("Updating host status after scanned failed due to internal error.")
            return DATABASE_UPDATE_ERROR

    def _update_host_scan(self, update_type, host_list, username=None):
        """
        Update hosts scan status and last_scan time
        Args:
            update_type (str): 'init' or 'finish'
            host_list (list): host id list
            username (str): user name
        Returns:

        """
        if update_type == "init":
            update_dict = {Host.status: "scanning", Host.last_scan: int(time())}
        elif update_type == "finish":
            update_dict = {Host.status: "done"}
        else:
            LOGGER.error("Given host scan update type '%s' is not in default type list "
                         "['init', 'finish']." % update_type)
            return SERVER_ERROR

        host_scan_query = self._query_scan_status_and_time(host_list, username)
        succeed_list = [row.host_id for row in host_scan_query]
        fail_list = set(host_list) - set(succeed_list)
        if fail_list:
            LOGGER.debug("No data found when setting the status of host: %s." % fail_list)
            if update_type == "init":
                return NO_DATA

        # update() is not applicable to 'in_' method without synchronize_session=False
        host_scan_query.update(update_dict, synchronize_session=False)
        return SUCCEED

    def _query_scan_status_and_time(self, host_list, username):
        """
        query host status and last_scan data of specific user
        Args:
            host_list (list): host id list, when empty, query all hosts
            username (str/None): user name
        Returns:
            sqlalchemy.orm.query.Query
        """
        filters = set()
        if host_list:
            filters.add(Host.host_id.in_(host_list))
        if username:
            filters.add(Host.user == username)

        hosts_status_query = self.session.query(Host.host_id, Host.status, Host.last_scan) \
            .filter(*filters)
        return hosts_status_query

    def save_scan_result(self, username, host_dict):
        """
        Save the scanned result to database.
        If one host id doesn't in Host table, then error will be raised and all insertion will
        be rolled back. So make sure Delete Host is forbidden during the scan.

        Args:
            username (str): username
            host_dict (dict): e.g.
                {
                    "id1": ["cve1", "cve2"],
                    "id2": [],
                }
        Returns:
            int
        """
        try:
            status_code = self._save_scan_result(username, host_dict)
            self.session.commit()
            LOGGER.debug("Finished saving scan result.")
            return status_code
        except SQLAlchemyError as error:
            self.session.rollback()
            LOGGER.error(error)
            LOGGER.error("Saving scan result failed due to internal error.")
            return DATABASE_INSERT_ERROR

    def _save_scan_result(self, username, host_dict):
        """
        Save host and cve's relationship into CveHostAssociation table.
        Delete the scanned hosts' previous cve record first, then add new cve record if
        cve list is not empty.

        Args:
            username (str): username
            host_dict (dict): record scanned hosts' cve list

        Returns:
            int
        """
        host_list = list(host_dict.keys())

        self.session.query(CveHostAssociation) \
            .filter(CveHostAssociation.host_id.in_(host_list)) \
            .delete(synchronize_session=False)

        exist_cve_query = self.session.query(Cve.cve_id)
        exist_cve_set = {row.cve_id for row in exist_cve_query}

        cve_host_rows = []
        valid_cve_set = set()
        for host_id, cve_list in host_dict.items():
            for cve_id in cve_list:
                if cve_id in exist_cve_set:
                    row = {"host_id": host_id, "cve_id": cve_id}
                    cve_host_rows.append(row)
                    valid_cve_set.add(cve_id)
                else:
                    LOGGER.debug("Cve '%s' in Scan result cannot be recorded because its data has "
                                 "not been imported yet." % cve_id)

        self.session.bulk_insert_mappings(CveHostAssociation, cve_host_rows)
        self._update_user_cve_status(username, valid_cve_set)
        return SUCCEED

    def _update_user_cve_status(self, username, cve_set):
        """
        update CveUserAssociation table, add new cve's record. If a cve doesn't exist in all
        hosts, still preserve it in the table
        Args:
            username (str): user name
            cve_set (set): the cve set to be added into CveUserAssociation table

        Returns:
            None
        """
        exist_cve_query = self.session.query(CveUserAssociation.cve_id) \
            .filter(CveUserAssociation.user_name == username)
        exist_cve = [row.cve_id for row in exist_cve_query]

        new_cve_list = list(cve_set-set(exist_cve))
        user_cve_rows = []
        for cve_id in new_cve_list:
            user_cve_rows.append({"cve_id": cve_id, "user_name": username,
                                  "status": "not reviewed"})
        self.session.bulk_insert_mappings(CveUserAssociation, user_cve_rows)

    def get_task_list(self, data):
        """
        Get the task list.
        Args:
            data (dict): parameter, e.g.
                {
                    "username": "admin",
                    "sort": "host_num",
                    "direction": "asc",
                    "page": 1,
                    "per_page": 10,
                    "filter": {
                        "task_name": "task2",
                        "task_type": ["repo"]
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
                            "task_id": "id1",
                            "task_name": "task1",
                            "task_type": "cve",
                            "description": "a long description",
                            "host_num": 12,
                            "create_time": 1111111111
                        }
                    ]
                }
        """
        result = {}
        try:
            result = self._get_processed_task_list(data)
            LOGGER.debug("Finished getting task list.")
            return SUCCEED, result
        except SQLAlchemyError as error:
            LOGGER.error(error)
            LOGGER.error("Getting task list failed due to internal error.")
            return DATABASE_QUERY_ERROR, result

    def _get_processed_task_list(self, data):
        """
        Get sorted, paged and filtered task list.

        Args:
            data(dict): sort, page and filter info

        Returns:
            dict
        """
        result = {
            "total_count": 0,
            "total_page": 0,
            "result": []
        }

        filters = self._get_task_list_filters(data.get("filter"))
        task_list_query = self._query_task_list(data["username"], filters)

        total_count = len(task_list_query.all())
        if not total_count:
            return result

        sort_column = getattr(Task, data.get("sort")) if "sort" in data else None
        direction, page, per_page = data.get('direction'), data.get('page'), data.get('per_page')

        processed_query, total_page = sort_and_page(task_list_query, sort_column,
                                                    direction, per_page, page)

        result['result'] = self._task_list_row2dict(processed_query)
        result['total_page'] = total_page
        result['total_count'] = total_count

        return result

    def _query_task_list(self, username, filters):
        """
        query needed task list
        Args:
            username (str): user name of the request
            filters (set): filter given by user

        Returns:
            sqlalchemy.orm.query.Query
        """
        task_list_query = self.session.query(Task.task_id, Task.task_name, Task.task_type,
                                             Task.description, Task.host_num, Task.create_time) \
            .filter(Task.username == username) \
            .filter(*filters)
        return task_list_query

    @staticmethod
    def _task_list_row2dict(rows):
        result = []
        for row in rows:
            task_info = {
                "task_id": row.task_id,
                "task_name": row.task_name,
                "task_type": row.task_type,
                "description": row.description,
                "host_num": row.host_num,
                "create_time": row.create_time
            }
            result.append(task_info)
        return result

    @staticmethod
    def _get_task_list_filters(filter_dict):
        """
        Generate filters

        Args:
            filter_dict(dict): filter dict to filter cve list, e.g.
                {
                    "task_name": "task2",
                    "task_type": ["cve", "repo"]
                }

        Returns:
            set
        """
        filters = set()
        if not filter_dict:
            return filters

        if filter_dict.get("task_name"):
            filters.add(Task.task_name.like("%" + filter_dict["task_name"] + "%"))
        if filter_dict.get("task_type"):
            filters.add(Task.task_type.in_(filter_dict["task_type"]))
        return filters

    def get_task_progress(self, data):
        """
        Get the task progress.
        Args:
            data (dict): parameter, e.g.
                {
                    "task_list": ["task1", "task2"],
                    "username": "admin"
                }
        Returns:
            int: status code
            dict: query result. e.g.
                {
                    "result": {
                        "task1": {
                            "succeed": 1,
                            "fail": 0,
                            "running": 11,
                            "unknown": 0
                        },
                        "task2": {
                            "succeed": 12,
                            "fail": 0,
                            "running": 0,
                            "unknown": 0
                        }
                    }
                }
        """
        result = {}
        try:
            status_code, result = self._get_processed_task_progress(data)
            LOGGER.debug("Finished getting task progress.")
            return status_code, result
        except (SQLAlchemyError, KeyError) as error:
            LOGGER.error(error)
            LOGGER.error("Getting task progress failed due to internal error.")
            return DATABASE_QUERY_ERROR, result

    def _get_processed_task_progress(self, data):
        """
        Get each task's progress
        Args:
            data (dict): task list info

        Returns:
            int: status code
            dict: query result
        """
        task_list = data["task_list"]
        username = data["username"]
        cve_task, repo_task = self._split_task_list(username, task_list)
        cve_task_progress = self._get_cve_task_progress(cve_task)
        repo_task_progress = self._get_repo_task_progress(repo_task)

        result = {}
        result.update(cve_task_progress)
        result.update(repo_task_progress)

        succeed_list = list(result.keys())
        fail_list = list(set(task_list) - set(succeed_list))
        if fail_list:
            LOGGER.debug("No data found when getting the progress of task: %s." % fail_list)

        status_dict = {"succeed_list": succeed_list, "fail_list": fail_list}
        status_code = judge_return_code(status_dict, NO_DATA)
        return status_code, {"result": result}

    def _split_task_list(self, username, task_list):
        """
        split task list based on task's type
        Args:
            username (str): user name
            task_list (list): task id list

        Returns:
            list: cve task list
            list: repo task list
        """
        cve_task = []
        repo_task = []

        # filter task's type in case of other type added into task table
        task_query = self.session.query(Task.task_id, Task.task_type) \
            .filter(Task.username == username, Task.task_id.in_(task_list),
                    Task.task_type.in_(task_types))

        for row in task_query:
            if row.task_type == "cve":
                cve_task.append(row.task_id)
            else:
                repo_task.append(row.task_id)
        return cve_task, repo_task

    @staticmethod
    def _get_status_result():
        def status_dict():
            return {"succeed": 0, "fail": 0, "running": 0, "unknown": 0}

        return defaultdict(status_dict)

    def _get_cve_task_progress(self, task_list):
        """
        get cve tasks' progress
        Args:
            task_list (list): cve tasks' id list

        Returns:
            dict: e.g.
                {"task1": {"succeed": 1, "fail": 0, "running": 10, "unknown": 1}}

        Raises:
            KeyError
        """

        def defaultdict_set():
            return defaultdict(set)

        tasks_dict = defaultdict(defaultdict_set)
        result = self._get_status_result()

        task_query = self._query_cve_task_host_status(task_list)
        for row in task_query:
            tasks_dict[row.task_id][row.host_id].add(row.status)

        for task_id, hosts_dict in tasks_dict.items():
            for status_set in hosts_dict.values():
                host_status = self._get_cve_task_status(status_set)
                result[task_id][host_status] += 1

        succeed_list = list(result.keys())
        fail_list = list(set(task_list) - set(succeed_list))
        if fail_list:
            LOGGER.error("CVE task '%s' exist but status data is not record." % fail_list)
        return result

    def _query_cve_task_host_status(self, task_list):
        """
        query host and CVE's relationship and status of required tasks
        Args:
            task_list (list): task id list

        Returns:
            sqlalchemy.orm.query.Query
        """
        task_query = self.session.query(TaskCveHostAssociation.task_id,
                                        TaskCveHostAssociation.host_id,
                                        TaskCveHostAssociation.status) \
            .filter(TaskCveHostAssociation.task_id.in_(task_list))
        return task_query

    @staticmethod
    def _get_cve_task_status(status_set):
        """
        get cve task's host or cve's overall status
        Args:
            status_set (set): host or cve's status set

        Returns:
            str
        """
        if "running" in status_set:
            return "running"
        if "unknown" in status_set:
            return "unknown"
        if "unfixed" in status_set:
            return "fail"
        return "succeed"

    def _get_repo_task_progress(self, task_list):
        """
        get repo tasks' progress
        Args:
            task_list (list): repo tasks' id list

        Returns:
            dict: e.g.
                {"task1": {"succeed": 1, "fail": 0, "running": 10, "unknown": 1}}

        Raises:
            KeyError
        """
        result = self._get_status_result()

        task_query = self._query_repo_task_host(task_list)
        for row in task_query:
            if row.status == "set":
                result[row.task_id]["succeed"] += 1
            elif row.status == "unset":
                result[row.task_id]["fail"] += 1
            elif row.status == "running":
                result[row.task_id]["running"] += 1
            elif row.status == "unknown":
                result[row.task_id]["unknown"] += 1
            else:
                LOGGER.error("Unknown repo task's host status '%s'" % row.status)

        succeed_list = list(result.keys())
        fail_list = list(set(task_list) - set(succeed_list))
        if fail_list:
            LOGGER.error("Repo task '%s' exist but status data is not record." % fail_list)
        return result

    def _query_repo_task_host(self, task_list):
        """
        query host and CVE's relationship and status of required tasks
        Args:
            task_list (list): task id list

        Returns:
            sqlalchemy.orm.query.Query
        """
        task_query = self.session.query(TaskHostRepoAssociation.task_id,
                                        TaskHostRepoAssociation.status) \
            .filter(TaskHostRepoAssociation.task_id.in_(task_list))
        return task_query

    def get_task_info(self, data):
        """
        Get a task's info
        Args:
            data (dict): parameter, e.g.
                {
                    "task_id": "id1",
                    "username": "admin"
                }
        Returns:
            int: status code
            dict: query result. e.g.
                {
                    "result": {
                        "task_name": "task",
                        "description": "a long description",
                        "host_num": 2,
                        "need_reboot": 1,
                        "auto_reboot": True,
                        "latest_execute_time": 1111111111
                    }
                }
        """
        result = {}
        try:
            status_code, result = self._get_processed_task_info(data)
            LOGGER.debug("Finished getting task info.")
            return status_code, result
        except SQLAlchemyError as error:
            LOGGER.error(error)
            LOGGER.error("Getting task info failed due to internal error.")
            return DATABASE_QUERY_ERROR, result

    def _get_processed_task_info(self, data):
        """
        query and process task info
        Args:
            data (dict): task id info

        Returns:
            int: status code
            dict: query result
        """
        task_id = data["task_id"]
        username = data["username"]

        task_info_query = self._query_task_info_from_mysql(username, task_id)
        if not task_info_query.all():
            LOGGER.debug("No data found when getting the info of task: %s." % task_id)
            return NO_DATA, {"result": {}}

        # raise exception when multiple record found
        task_info_data = task_info_query.one()

        info_dict = self._task_info_row2dict(task_info_data)
        return SUCCEED, {"result": info_dict}

    def _query_task_info_from_mysql(self, username, task_id):
        """
        query needed task info
        Args:
            username (str): user name of the request
            task_id (str): task id

        Returns:
            sqlalchemy.orm.query.Query
        """
        task_info_query = self.session.query(Task.task_name, Task.description, Task.host_num,
                                             Task.need_reboot, Task.auto_reboot,
                                             Task.latest_execute_time) \
            .filter(Task.task_id == task_id, Task.username == username)
        return task_info_query

    @staticmethod
    def _task_info_row2dict(row):
        task_info = {
            "task_name": row.task_name,
            "description": row.description,
            "host_num": row.host_num,
            "need_reboot": row.need_reboot,
            "auto_reboot": row.auto_reboot,
            "latest_execute_time": row.latest_execute_time
        }
        return task_info

    def get_cve_task_info(self, data):
        """
        Get the specific info about the cve fixing task.

        Args:
            data (dict): parameter, e.g.
                {
                    "task_id": "id1",
                    "sort": "host_num",
                    "direction": "asc",
                    "page": 1,
                    "per_page": 10,
                    "username": "admin",
                    "filter": {
                        "cve_id": "",
                        "reboot": True,
                        "status": []
                    }
                }

        Returns:
            int: status code
            dict: task's cve info. e.g.
                {
                    "total_count": 1,
                    "total_page": 1,
                    "result": [{
                        "cve_id": "id1",
                        "package": "tensorflow",
                        "reboot": True,
                        "host_num": 3,
                        "status": "running"
                    }]
                }
        """
        result = {}
        try:
            result = self._get_processed_cve_task(data)
            LOGGER.debug("Finished getting task's cve info.")
            return SUCCEED, result
        except SQLAlchemyError as error:
            LOGGER.error(error)
            LOGGER.error("Getting task's cve info failed due to internal error.")
            return DATABASE_QUERY_ERROR, result

    def _get_processed_cve_task(self, data):
        """
        Query and process cve task's cve info
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

        task_id = data["task_id"]
        filter_dict = data.get("filter", {})
        filters = self._get_cve_task_filters(filter_dict)
        task_cve_query = self._query_cve_task(data["username"], task_id, filters)
        cve_info_list = self._process_cve_task_data(task_cve_query, filter_dict)

        total_count = len(cve_info_list)
        # NO_DATA code is NOT returned because no data situation here is normal with filter
        if not total_count:
            return result

        processed_result, total_page = self._sort_and_page_task_cve(cve_info_list, data)
        result['result'] = processed_result
        result['total_page'] = total_page
        result['total_count'] = total_count

        return result

    @staticmethod
    def _get_cve_task_filters(filter_dict):
        """
        Generate filters to filter cve task's cve info
        (filter by status will be manually implemented)
        Args:
            filter_dict(dict): filter dict to filter cve task's cve info, e.g.
                {
                    "cve_id": "",
                    "reboot": True,
                    "status": [""]
                }

        Returns:
            set
        """
        filters = set()

        if filter_dict.get("cve_id"):
            filters.add(Cve.cve_id.like("%" + filter_dict["cve_id"] + "%"))
        if filter_dict.get("reboot"):
            filters.add(Cve.reboot == filter_dict["reboot"])
        return filters

    def _query_cve_task(self, username, task_id, filters):
        """
        query needed cve task's cve info
        Args:
            username (str): user name of the request
            task_id (str): task id
            filters (set): filter given by user

        Returns:
            sqlalchemy.orm.query.Query. row structure:
                {
                    "cve_id": "CVE-2021-0001",
                    "package": "tensorflow",
                    "reboot": True,
                    "host_id": "id1",
                    "status": "fixed"
                }
        """
        task_cve_query = self.session.query(Cve.cve_id, Cve.reboot, CveAffectedPkgs.package,
                                            TaskCveHostAssociation.host_id,
                                            TaskCveHostAssociation.status) \
            .join(TaskCveHostAssociation, TaskCveHostAssociation.cve_id == Cve.cve_id) \
            .join(CveAffectedPkgs, CveAffectedPkgs.cve_id == Cve.cve_id) \
            .join(Task, Task.task_id == TaskCveHostAssociation.task_id) \
            .filter(Task.task_id == task_id, Task.username == username) \
            .filter(*filters)

        return task_cve_query

    def _process_cve_task_data(self, task_cve_query, filter_dict):
        """
        process task cve query data, get each cve's total status and host_num, then filter by status
        Args:
            task_cve_query (sqlalchemy.orm.query.Query): query result of cve task's cve info
                each row's structure:
                    {
                        "cve_id": "CVE-2021-0001",
                        "package": "tensorflow",
                        "reboot": True,
                        "host_id": "id1",
                        "status": "fixed"
                    }
            filter_dict (None/dict): the status user want
        Returns:
            list. e.g.
                [{
                    "cve_id": "CVE-2021-0001",
                    "package": "tensorflow",
                    "reboot": True,
                    "host_num": 3,
                    "status": "running"
                }]
        """
        need_status = filter_dict.get("status") if filter_dict else None
        cve_info_list = []
        cve_dict = {}

        for row in task_cve_query:
            cve_id = row.cve_id
            if cve_id not in cve_dict:
                cve_dict[cve_id] = {"package": {row.package}, "reboot": row.reboot,
                                    "host_set": {row.host_id}, "status_set": {row.status}}
            else:
                cve_dict[cve_id]["package"].add(row.package)
                cve_dict[cve_id]["host_set"].add(row.host_id)
                cve_dict[cve_id]["status_set"].add(row.status)

        if isinstance(need_status, list):
            if not need_status:
                return cve_info_list
            for cve_id, cve_info in cve_dict.items():
                cve_status = self._get_cve_task_status(cve_info.pop("status_set"))
                if cve_status in need_status:
                    cve_info["cve_id"] = cve_id
                    cve_info["package"] = ','.join(list(cve_info["package"]))
                    cve_info["host_num"] = len(cve_info.pop("host_set"))
                    cve_info["status"] = cve_status
                    cve_info_list.append(cve_info)
        else:
            for cve_id, cve_info in cve_dict.items():
                cve_info["cve_id"] = cve_id
                cve_info["package"] = ','.join(list(cve_info["package"]))
                cve_info["host_num"] = len(cve_info.pop("host_set"))
                cve_info["status"] = self._get_cve_task_status(cve_info.pop("status_set"))
                cve_info_list.append(cve_info)
        return cve_info_list

    @staticmethod
    def _sort_and_page_task_cve(cve_info_list, data):
        """
        sort and page cve task's cve info
        Args:
            cve_info_list (list): cve task's cve info list. not empty.
            data (dict): parameter, e.g.
                {
                    "task_id": "id1",
                    "sort": "host_num",
                    "direction": "asc",
                    "page": 1,
                    "per_page": 10,
                    "username": "admin",
                    "filter": {
                        "cve_id": "",
                        "reboot": True,
                        "status": []
                    }
                }

        Returns:
            list: sorted cve info list
            int: total page
        """
        page = data.get('page')
        per_page = data.get('per_page')
        reverse = False
        if data.get("sort") == "host_num" and data.get("direction") == "desc":
            reverse = True

        total_page = 1
        total_count = len(cve_info_list)

        cve_info_list.sort(key=lambda cve_info: cve_info["host_num"], reverse=reverse)

        if page and per_page:
            total_page = math.ceil(total_count / per_page)
            return cve_info_list[per_page*(page-1): per_page*page], total_page

        return cve_info_list, total_page

    def get_task_cve_status(self, data):
        """
        Get the status of each host of the cve in the task

        Args:
            data (dict): parameter, e.g.
                {
                    "task_id": "id1",
                    "cve_list": ["cve1"],  // if empty, query all cve
                    "username": "admin"
                }

        Returns:
            int: status code
            dict: query result. e.g.
                {
                    "result": {
                        "cve1": [
                            {
                                "host_id": "id1",
                                "host_name": "name1",
                                "host_ip": "127.0.0.1",
                                "status": "running"
                            }
                        ]
                    }
                }
        """
        result = {}
        try:
            status_code, result = self._get_processed_task_cve_status(data)
            LOGGER.debug("Finished getting the status of each host of the cve in cve task")
            return status_code, result
        except SQLAlchemyError as error:
            LOGGER.error(error)
            LOGGER.error("Getting the status of each host of the cve in cve task failed "
                         "due to internal error.")
            return DATABASE_QUERY_ERROR, result

    def _get_processed_task_cve_status(self, data):
        """
        query and process the hosts' fixing status of cve in a cve task
        Args:
            data (dict): parameter

        Returns:
            dict
        """
        task_id = data["task_id"]
        cve_list = data["cve_list"]
        username = data["username"]
        status_query = self._query_cve_task_cve_status(username, task_id, cve_list, with_host=True)

        if not status_query.all():
            LOGGER.debug("No data found when getting the hosts' fixing status of cve '%s' "
                         "in cve task: %s." % (cve_list, task_id))
            return NO_DATA, {"result", {}}

        result = defaultdict(list)
        for row in status_query:
            host_dict = self._cve_host_status_row2dict(row)
            result[row.cve_id].append(host_dict)

        succeed_list = list(result.keys())
        fail_list = list(set(cve_list) - set(succeed_list))

        if fail_list:
            LOGGER.debug("No data found when getting the hosts' fixing status of cve '%s' "
                         "in cve task: %s." % (fail_list, task_id))
            return PARTIAL_SUCCEED, {"result": dict(result)}

        return SUCCEED, {"result": dict(result)}

    def _query_cve_task_cve_status(self, username, task_id, cve_list, with_host=False):
        """
        query the hosts' fixing status of given cve list in a cve task
        Args:
            username (str): user name of the request
            task_id (str): task id
            cve_list (list): cve id list, if empty, query all cve
            with_host (bool): with host info or not

        Returns:
            sqlalchemy.orm.query.Query
        """
        filters = {Task.username == username, TaskCveHostAssociation.task_id == task_id}
        if cve_list:
            filters.add(TaskCveHostAssociation.cve_id.in_(cve_list))

        if with_host:
            status_query = self.session.query(TaskCveHostAssociation.status,
                                              TaskCveHostAssociation.cve_id,
                                              TaskCveHostAssociation.host_id,
                                              TaskCveHostAssociation.host_name,
                                              TaskCveHostAssociation.public_ip) \
                .join(Task, Task.task_id == TaskCveHostAssociation.task_id) \
                .filter(*filters)
        else:
            status_query = self.session.query(TaskCveHostAssociation.status,
                                              TaskCveHostAssociation.cve_id) \
                .join(Task, Task.task_id == TaskCveHostAssociation.task_id) \
                .filter(*filters)
        return status_query

    @staticmethod
    def _cve_host_status_row2dict(row):
        host_status = {
            "host_id": row.host_id,
            "host_name": row.host_name,
            "host_ip": row.public_ip,
            "status": row.status
        }
        return host_status

    def get_task_cve_progress(self, data):
        """
        Get progress and status of each cve in the task.

        Args:
            data (dict): parameter, e.g.
                {
                    "task_id": "id1",
                    "cve_list": ["cve1"], if empty, query all cve
                    "username": "admin"
                }

        Returns:
            int: status code
            dict: cve's progress and status info. e.g.
                {
                    "result": {
                        "cve1": {
                            "progress": 1,
                            "status": "running"
                        }
                    }
                }
        """
        result = {}
        try:
            status_code, result = self._get_processed_task_cve_progress(data)
            LOGGER.debug("Finished getting the progress and status of the cve in cve task")
            return status_code, result
        except SQLAlchemyError as error:
            LOGGER.error(error)
            LOGGER.error("Getting the progress and status of the cve in cve task failed "
                         "due to internal error.")
            return DATABASE_QUERY_ERROR, result

    def _get_processed_task_cve_progress(self, data):
        """
        query and process the progress and status of cve in the cve task.
        Args:
            data (dict): parameter

        Returns:
            dict
        """
        task_id = data["task_id"]
        cve_list = data["cve_list"]
        username = data["username"]
        progress_query = self._query_cve_task_status_progress(username, task_id, cve_list)

        if not progress_query.all():
            LOGGER.debug("No data found when getting the status and progress of cve '%s' "
                         "in cve task: %s." % (cve_list, task_id))
            return NO_DATA, {"result": {}}

        result = {}
        for row in progress_query:
            cve_id = row.cve_id
            if cve_id not in result:
                result[cve_id] = {"progress": row.progress, "status": {row.status}}
            else:
                result[cve_id]["status"].add(row.status)

        for cve_info in result.values():
            status = cve_info["status"]
            cve_info["status"] = self._get_cve_task_status(status)

        succeed_list = list(result.keys())
        fail_list = list(set(cve_list) - set(succeed_list))

        if fail_list:
            LOGGER.debug("No data found when getting the status and progress of cve '%s' "
                         "in cve task: %s." % (fail_list, task_id))
            return PARTIAL_SUCCEED, {"result": result}

        return SUCCEED, {"result": result}

    def _query_cve_task_status_progress(self, username, task_id, cve_list):
        """
        query cve task's assigned cve's status and progress
        Args:
            username (str): user name
            task_id (str): task id
            cve_list (list): cve id list, if empty, query all cve

        Returns:
            sqlalchemy.orm.query.Query
        """
        filters = {Task.username == username, TaskCveHostAssociation.task_id == task_id}
        if cve_list:
            filters.add(TaskCveHostAssociation.cve_id.in_(cve_list))

        task_query = self.session.query(TaskCveHostAssociation.cve_id,
                                        TaskCveHostAssociation.status,
                                        CveTaskAssociation.progress) \
            .join(Task, Task.task_id == TaskCveHostAssociation.task_id) \
            .join(CveTaskAssociation, (CveTaskAssociation.task_id == TaskCveHostAssociation.task_id)
                  & (CveTaskAssociation.cve_id == TaskCveHostAssociation.cve_id)) \
            .filter(*filters)
        return task_query

    def get_rollback_cve_list(self, data):
        """
        Just get the cve id list whose status is "succeed" and "fail", according to task id and
        username, the interface is used to verify the parameter for rollback.

        Args:
            data (dict): e.g.
                {
                    "task_id": "aa",
                    "username": "admin"
                }

        Returns:
            list
        """
        result = []
        try:
            result = self._get_rollback_cve_list(data)
            LOGGER.debug("Finished getting the cve task list which may need roll back.")
            return result
        except SQLAlchemyError as error:
            LOGGER.error(error)
            LOGGER.error("Getting the cve task list which may need roll back failed "
                         "due to internal error.")
            return result

    def _get_rollback_cve_list(self, data):
        """
        query the cve id whose status is "succeed" and "fail"
        """
        username = data["username"]
        task_id = data["task_id"]
        status_query = self._query_cve_task_cve_status(username, task_id, [])

        status_dict = defaultdict(set)
        for row in status_query:
            status_dict[row.cve_id].add(row.status)

        cve_list = []
        for cve_id, status_set in status_dict.items():
            cve_status = self._get_cve_task_status(status_set)
            if cve_status in ["succeed", "fail"]:
                cve_list.append(cve_id)

        return cve_list

    def get_cve_basic_info(self, task_id):
        """
        Get cve task basic info of the task id, for generating the playbook and
        inventory.

        Args:
            task_id (str): task_id

        Returns:
            int: status code
            list: e.g.
                [
                    {
                        "cve_id": "cve-11-11",
                        "host_info": [
                            {
                                "host_name": "name1",
                                "host_ip": "11.1.1.1",
                                "host_id": ""
                            }
                        ],
                        "reboot": True
                    }
                ]
        """
        result = []
        try:
            status_code, result = self._get_processed_cve_basic_info(task_id)
            LOGGER.debug("Finished getting the basic info of cve task.")
            return status_code, result
        except SQLAlchemyError as error:
            LOGGER.error(error)
            LOGGER.error("Getting the basic info of cve task failed due to internal error.")
            return DATABASE_QUERY_ERROR, result

    def _get_processed_cve_basic_info(self, task_id):
        """
        query and process cve task's basic info
        Args:
            task_id (str): task id

        Returns:
            int
            list
        """
        task_query = self._query_cve_task_basic_info(task_id)
        if not task_query.all():
            LOGGER.debug("No data found when getting the basic info of cve task: %s." % task_id)
            return NO_DATA, []

        cve_dict = {}

        for row in task_query:
            if row.cve_id not in cve_dict:
                cve_dict[row.cve_id] = {"host_info": [], "reboot": row.reboot, "cve_id": row.cve_id}
            host_info = {"host_id": row.host_id, "host_name": row.host_name,
                         "host_ip": row.public_ip}
            cve_dict[row.cve_id]["host_info"].append(host_info)

        return SUCCEED, list(cve_dict.values())

    def _query_cve_task_basic_info(self, task_id):
        """
        query cve task's basic info
        Args:
            task_id (str): task id

        Returns:
            sqlalchemy.orm.query.Query
        """
        task_query = self.session.query(TaskCveHostAssociation.cve_id,
                                        TaskCveHostAssociation.host_name,
                                        TaskCveHostAssociation.host_id,
                                        TaskCveHostAssociation.public_ip,
                                        CveTaskAssociation.reboot) \
            .join(CveTaskAssociation, (CveTaskAssociation.task_id == TaskCveHostAssociation.task_id)
                  & (CveTaskAssociation.cve_id == TaskCveHostAssociation.cve_id))\
            .filter(TaskCveHostAssociation.task_id == task_id)
        return task_query

    def update_cve_status(self, task_id, cve_id, host_id, status):
        """
        Every time a cve in a host has been tried to be fixed or rollbacked, update the status

        Args:
            task_id (str): task id
            cve_id (str): cve id
            host_id (str): host id
            status (str): status

        Returns:
            int: status code
        """
        try:
            status_code = self._update_cve_host_status(task_id, cve_id, host_id, status)
            if status_code != SUCCEED:
                return status_code
            self.session.commit()
            LOGGER.debug("Finished updating cve host status.")
            return SUCCEED
        except SQLAlchemyError as error:
            self.session.rollback()
            LOGGER.error(error)
            LOGGER.error("Updating cve host status failed due to internal error.")
            return DATABASE_UPDATE_ERROR

    def _update_cve_host_status(self, task_id, cve_id, host_id, status):
        """
        update a cve's one host's fix status of a cve task
        """
        status_query = self.session.query(TaskCveHostAssociation) \
            .filter(TaskCveHostAssociation.task_id == task_id,
                    TaskCveHostAssociation.cve_id == cve_id,
                    TaskCveHostAssociation.host_id == host_id)

        if not status_query.all():
            LOGGER.error("Updating cve host status failed due to no data found.")
            return NO_DATA
        if len(status_query.all()) > 1:
            LOGGER.error("Updating cve host status failed due to internal error.")
            return DATABASE_UPDATE_ERROR

        status_query.one().status = status
        return SUCCEED

    def set_cve_progress(self, task_id, cve_list, method='add'):
        """
        Everytime a task completed, update the progress, add 1 or fill up

        Args:
            task_id (str): task id
            cve_list (list): cve id list, it can be empty which means all cve id.
            method (str, optional): 'add' means adding 1, 'zero' means setting to 0, 'fill' means
                                    filling up, Default to add.

        Returns:
            int: status code
        """
        try:
            status_code = self._set_cve_progress(task_id, cve_list, method)
            if status_code != SUCCEED:
                return status_code
            self.session.commit()
            LOGGER.debug("Finished setting cve fixing progress.")
            return SUCCEED
        except SQLAlchemyError as error:
            self.session.rollback()
            LOGGER.error(error)
            LOGGER.error("Setting cve fixing progress failed due to internal error.")
            return DATABASE_UPDATE_ERROR

    def _set_cve_progress(self, task_id, cve_list, method):
        """
        set cve's fixing progress based on method
        """
        filters = {CveTaskAssociation.task_id == task_id}
        if cve_list:
            filters.add(CveTaskAssociation.cve_id.in_(cve_list))

        progress_query = self.session.query(CveTaskAssociation.progress,
                                            CveTaskAssociation.host_num) \
            .filter(*filters)

        if method == "add":
            progress_query.update({CveTaskAssociation.progress: min(CveTaskAssociation.progress + 1,
                                                                    CveTaskAssociation.host_num)},
                                  synchronize_session=False)
        elif method == "fill":
            progress_query.update({CveTaskAssociation.progress: CveTaskAssociation.host_num},
                                  synchronize_session=False)
        elif method == "zero":
            progress_query.update({CveTaskAssociation.progress: 0}, synchronize_session=False)
        else:
            LOGGER.error("Set cve progress with unknown method '%s'." % method)
            return SERVER_ERROR
        return SUCCEED

    def init_cve_task(self, task_id, cve_list):
        """
        Before fixing or rollbacking cve, set related host status to 'running', and set progress
        to 0, these two actions are placed together for they can be rollbacked together when one
        of them failed.

        Args:
            task_id (str): task id
            cve_list (list): cve id list, it can be empty which means all cve id.

        Returns:
            int: status code
        """
        try:
            status_code = self._init_cve_task(task_id, cve_list)
            self.session.commit()
            LOGGER.debug("Finished init cve task's status and progress.")
            return status_code
        except SQLAlchemyError as error:
            self.session.rollback()
            LOGGER.error(error)
            LOGGER.error("Init cve task's status and progress failed due to internal error.")
            return DATABASE_UPDATE_ERROR

    def _init_cve_task(self, task_id, cve_list):
        """
        set cve's related host's status to running, and set the cve's progress to 0
        """
        # set status to running
        filters = {TaskCveHostAssociation.task_id == task_id}
        if cve_list:
            filters.add(TaskCveHostAssociation.cve_id.in_(cve_list))

        status_query = self.session.query(TaskCveHostAssociation.status).filter(*filters)
        status_query.update({TaskCveHostAssociation.status: "running"}, synchronize_session=False)

        # set progress to 0
        filters = {CveTaskAssociation.task_id == task_id}
        if cve_list:
            filters.add(CveTaskAssociation.cve_id.in_(cve_list))

        status_query = self.session.query(CveTaskAssociation.progress).filter(*filters)
        status_query.update({CveTaskAssociation.progress: 0}, synchronize_session=False)

        return SUCCEED

    def fix_task_status(self, task_id, task_type):
        """
        After executing the task, in case that internal error occured, set the status of
        running host in the task to 'unknown'.

        Args:
            task_id (str)
            task_type (str)

        Returns:
            int: status code
        """
        try:
            status_code = self._set_failed_task_status(task_id, task_type)
            if status_code != SUCCEED:
                return status_code
            self.session.commit()
            LOGGER.debug("Finished setting task %s status to unknown." % task_id)
            return SUCCEED
        except SQLAlchemyError as error:
            self.session.rollback()
            LOGGER.error(error)
            LOGGER.error("Setting task %s status to unknown failed due to internal error." % task_id)
            return DATABASE_UPDATE_ERROR

    def _set_failed_task_status(self, task_id, task_type):
        """
        set failed task's running hosts' status to "unknown"
        """
        if task_type == "cve":
            host_query = self.session.query(TaskCveHostAssociation.status) \
                .filter(TaskCveHostAssociation.task_id == task_id,
                        TaskCveHostAssociation.status == "running")
            host_query.update({TaskCveHostAssociation.status: "unknown"}, synchronize_session=False)
        elif task_type == "repo":
            host_query = self.session.query(TaskHostRepoAssociation.status) \
                .filter(TaskHostRepoAssociation.task_id == task_id,
                        TaskHostRepoAssociation.status == "running")
            host_query.update({TaskHostRepoAssociation.status: "unknown"}, synchronize_session=False)
        else:
            LOGGER.error("Unknown task type '%s' when setting its status." % task_type)
            return SERVER_ERROR

        return SUCCEED

    def get_repo_task_info(self, data):
        """
        Get repo task info.

        Args:
            data (dict): e.g.
                {
                    "username": "admin",
                    "task_id": "",
                    "page": 1,
                    "per_page": 10,
                    "filter": {
                        "host_name": "",
                        "status": []
                    }
                }

        Returns:
            int: status code
            dict. e.g.
                {
                    "result": [
                        {
                            "host_id": "id1",
                            "host_name": "host1",
                            "host_ip": "id1",
                            "repo_name": "repo1",
                            "status": "running"
                        }
                    ],
                    "total_count": 1,
                    "total_page": 1
                }
        """
        result = {}
        try:
            result = self._get_processed_repo_task(data)
            LOGGER.debug("Finished getting repo task info.")
            return SUCCEED, result
        except SQLAlchemyError as error:
            LOGGER.error(error)
            LOGGER.error("Getting repo task info failed due to internal error.")
            return DATABASE_QUERY_ERROR, result

    def _get_processed_repo_task(self, data):
        """
        query and process repo task info
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

        task_id = data["task_id"]
        filter_dict = data.get("filter")
        filters = self._get_repo_task_filters(filter_dict)
        repo_task_query = self._query_repo_task(data["username"], task_id, filters)

        total_count = len(repo_task_query.all())
        # NO_DATA code is NOT returned because no data situation here is normal with filter
        if not total_count:
            return result

        page = data.get('page')
        per_page = data.get('per_page')
        processed_query, total_page = sort_and_page(repo_task_query, None, None, per_page, page)

        result['result'] = self._repo_task_info_row2dict(processed_query)
        result['total_page'] = total_page
        result['total_count'] = total_count

        return result

    def _query_repo_task(self, username, task_id, filters):
        """
        query needed repo task's host info
        Args:
            username (str): user name of the request
            task_id (str): task id
            filters (set): filter given by user

        Returns:
            sqlalchemy.orm.query.Query. row structure:
                {
                    "host_id": "id1",
                    "host_name": "name1",
                    "host_ip": "ip1",
                    "repo_name": "repo1",
                    "status": "unset"
                }
        """
        task_repo_query = self.session.query(TaskHostRepoAssociation.host_id,
                                             TaskHostRepoAssociation.host_name,
                                             TaskHostRepoAssociation.public_ip,
                                             TaskHostRepoAssociation.repo_name,
                                             TaskHostRepoAssociation.status) \
            .join(Task, Task.task_id == TaskHostRepoAssociation.task_id) \
            .filter(Task.username == username, TaskHostRepoAssociation.task_id == task_id) \
            .filter(*filters)

        return task_repo_query

    @staticmethod
    def _get_repo_task_filters(filter_dict):
        """
        Generate filters to filter repo task's host info
        Args:
            filter_dict(dict): filter dict to filter repo task's host info, e.g.
                {
                    "host_name": "name1",
                    "status": []
                }

        Returns:
            set
        """
        filters = set()
        if not filter_dict:
            return filters

        if filter_dict.get("host_name"):
            filters.add(TaskHostRepoAssociation.host_name.like("%" + filter_dict["host_name"] + "%"))
        if filter_dict.get("status"):
            filters.add(TaskHostRepoAssociation.status.in_(filter_dict["status"]))
        return filters

    @staticmethod
    def _repo_task_info_row2dict(rows):
        result = []
        for row in rows:
            host_info = {
                "host_id": row.host_id,
                "host_name": row.host_name,
                "host_ip": row.public_ip,
                "repo_name": row.repo_name,
                "status": row.status
            }
            result.append(host_info)
        return result

    def set_host_repo(self, repo_name, host_list):
        """
        set repo name to hosts when "set repo" task finished successfully.
        Args:
            repo_name (str): repo name
            host_list (list): host id list

        Returns:
            int
        """
        try:
            self._update_host_repo(repo_name, host_list)
            self.session.commit()
            LOGGER.debug("Finished setting repo name to hosts when task finished.")
            return SUCCEED
        except SQLAlchemyError as error:
            self.session.rollback()
            LOGGER.error(error)
            LOGGER.error("Setting repo name to hosts when task finished failed due to "
                         "internal error.")
            return DATABASE_UPDATE_ERROR

    def _update_host_repo(self, repo_name, host_list):
        """
        set repo name to relative hosts
        """
        self.session.query(Host.repo_name)\
            .filter(Host.host_id.in_(host_list))\
            .update({Host.repo_name: repo_name}, synchronize_session=False)

    def set_repo_status(self, task_id, host_list, status):
        """
        Everytime a repo setting task will be executed or has been completed,
        update the related status.

        Args:
            task_id (str)
            host_list (list): host id list, can be empty, which means all host.
            status (str): can be "set", "unset", "running", "unknown"
            ('unknown' when task has some error, but prefer using 'fix_task_status' in this case)

        Returns:
            int: status code
        """
        try:
            self._update_repo_host_status(task_id, host_list, status)
            self.session.commit()
            LOGGER.debug("Finished updating repo host status.")
            return SUCCEED
        except SQLAlchemyError as error:
            self.session.rollback()
            LOGGER.error(error)
            LOGGER.error("Updating repo host status failed due to internal error.")
            return DATABASE_UPDATE_ERROR

    def _update_repo_host_status(self, task_id, host_list, status):
        """
        update a host's repo setting status of a repo task
        """
        filters = {TaskHostRepoAssociation.task_id == task_id}
        if host_list:
            filters.add(TaskHostRepoAssociation.host_id.in_(host_list))

        status_query = self.session.query(TaskHostRepoAssociation.status).filter(*filters)
        status_query.update({TaskHostRepoAssociation.status: status}, synchronize_session=False)

    def get_task_type(self, task_id, username):
        """
        Return the type of the task, return None if check failed.

        Args:
            task_id (str): task id
            username (str): user name

        Returns:
            int
            str or None
        """
        try:
            status_code, task_type = self._get_task_type(task_id, username)
            if status_code == SUCCEED:
                LOGGER.debug("Finished getting task's type.")
            return task_type
        except SQLAlchemyError as error:
            LOGGER.error(error)
            LOGGER.error("Getting task's type failed due to internal error.")
            return None

    def _get_task_type(self, task_id, username):
        """
        query task's type.
        """
        type_query = self.session.query(Task.task_type) \
            .filter(Task.task_id == task_id, Task.username == username)

        if not type_query.all():
            LOGGER.error("Querying type of task '%s' failed due to no data found." % task_id)
            return NO_DATA, None
        if len(type_query.all()) > 1:
            LOGGER.error("Querying type of task '%s' failed due to internal error." % task_id)
            return DATABASE_QUERY_ERROR, None

        task_type = type_query.one().task_type
        return SUCCEED, task_type

    def update_task_execute_time(self, task_id, cur_time):
        """
        Update task latest execute time when task is executed
        Args:
            task_id (str): task id
            cur_time (int): latest execute time

        Returns:
            int: status code
        """
        try:
            status_code = self._update_latest_execute_time(task_id, cur_time)
            if status_code != SUCCEED:
                return status_code
            self.session.commit()
            LOGGER.debug("Finished updating task's latest execute time.")
            return status_code
        except SQLAlchemyError as error:
            self.session.rollback()
            LOGGER.error(error)
            LOGGER.error("Updating task's latest execute time failed due to internal error.")
            return DATABASE_UPDATE_ERROR

    def _update_latest_execute_time(self, task_id, cur_time):
        """
        update a task's latest execute time
        """
        status_query = self.session.query(Task).filter(Task.task_id == task_id)

        if not status_query.all():
            LOGGER.error("Updating latest execute time of task '%s' failed due to no data found."
                         % task_id)
            return NO_DATA
        if len(status_query.all()) > 1:
            LOGGER.error("Updating latest execute time of task '%s' failed due to internal error."
                         % task_id)
            return DATABASE_UPDATE_ERROR

        status_query.one().latest_execute_time = cur_time
        return SUCCEED

    def check_task_status(self, task_id, task_type):
        """
        check the task is open for execute or not
        Args:
            task_id (str): task id
            task_type (str): for now, 'cve' or 'repo'

        Returns:
            bool
        """
        if task_type == 'cve':
            task_progress = self._get_cve_task_progress([task_id])
        elif task_type == 'repo':
            task_progress = self._get_repo_task_progress([task_id])
        else:
            LOGGER.error("Unknown task type '%s' was given when checking task '%s' status."
                         % (task_type, task_id))
            return True

        if task_progress[task_id]["running"]:
            return False
        return True


class TaskEsProxy(ElasticsearchProxy):
    def get_package_info(self, data):
        """
        Get package info of the cve.

        Args:
            data (list): e.g.
                [
                    {
                        "cve_id": "cve-11-11",
                        "host_info": [
                            {
                                "host_name": "name1",
                                "host_ip": "11.1.1.1",
                                "host_id": "1"
                            }
                        ]
                    }
                ]

        Returns:
            int: status code
            dict: package info. e.g.
                    {
                        "cve-11-11": ["xx.rpm", "yy"],
                        "cve-11-12": ["x"]
                    }
        """
        return SUCCEED, {}

    def save_task_info(self, task_id, playbook=None, inventory=None, log=None):
        """
        Every time playbook, inventory, log are generated, save them to es database.

        Args:
            task_id (str): task id
            playbook (str): ansible playbook
            inventory (str): ansible inventory
            log (str): task's log

        Returns:
            int: status code
        """
        operation_code, task_exist = self.exists(TASK_INDEX, document_id=task_id)
        if not operation_code:
            LOGGER.error("Failed to query whether the task exists or not due to internal error")
            return DATABASE_INSERT_ERROR

        if not task_exist:
            LOGGER.error("Task doesn't exist when save task info into es.")
            return DATABASE_INSERT_ERROR

        operation_code = self._update_task(task_id, playbook, inventory, log)

        if operation_code:
            LOGGER.debug("Finished saving task info into es.")
            return SUCCEED

        LOGGER.error("Saving task info into es failed due to internal error.")
        return DATABASE_INSERT_ERROR

    def _update_task(self, task_id, playbook, inventory, log):
        """
        update task info into es.
        Args:
            task_id (str/None): task id
            playbook (str/None): task's ansible playbook
            inventory (str/None): ansible inventory
            log (str/None): task log

        Returns:
            bool
        """
        task_body = {"task_id": task_id}
        if playbook is not None:
            task_body["playbook"] = playbook
        if inventory is not None:
            task_body["inventory"] = inventory
        if log is not None:
            task_body["log"] = log
        action = [{"_id": task_id, "doc": task_body}]
        operation_code = self.update_bulk(TASK_INDEX, action)
        return operation_code

    def _query_task_info_from_es(self, task_id, username=None, source=True):
        """
        query task's info from elasticsearch
        Args:
            task_id (str): task id
            username (str/None): user name, used for authorisation check
            source (bool/list): list of source

        Returns:
            bool
            dict
        """
        query_body = self._general_body()
        if username:
            query_body['query']['bool']['must'].extend(
                [{"term": {"_id": task_id}}, {"term": {"username": username}}])
        else:
            query_body['query']['bool']['must'].append(
                {"term": {"_id": task_id}})
        operation_code, res = self.query(TASK_INDEX, query_body, source)
        return operation_code, res

    def get_task_ansible_info(self, task_id, info_type, username=None):
        """
        Get task's ansible info (playbook/inventory/log) from es

        Args:
            task_id (str): task id
            info_type (str): 'playbook'/'inventory'/'log'
            username (str): user name, used for authorisation check

        Returns:
            int: status code
            str: needed task info
        """
        if info_type not in ["playbook", "inventory", "log"]:
            LOGGER.error("Unknown task info type '%s' were given when getting info of task '%s'."
                         % (info_type, task_id))
            return PARAM_ERROR, ""

        operation_code, res = self._query_task_info_from_es(task_id, username, [info_type])

        if not operation_code:
            LOGGER.debug("Querying %s info of task '%s' failed due to internal error."
                         % (info_type, task_id))
            return DATABASE_QUERY_ERROR, ""

        if not res["hits"]["hits"]:
            LOGGER.debug("No data found when getting %s info of task '%s'." % (info_type, task_id))
            return NO_DATA, ""

        task_info = res["hits"]["hits"][0]["_source"][info_type]
        LOGGER.debug("Querying task %s succeed." % info_type)
        return SUCCEED, task_info

    def get_task_cve_result(self, data):
        """
        Get the result of each cve in the task, in addition to basic info of the task.

        Args:
            data (dict): parameter. e.g.
                {
                    "username": "admin",
                    "task_id": "",
                    "cve_list": []  // if empty, return all cve's result
                }

        Returns:
            int: status code
            dict: query result. e.g.
                {
                    "result": {
                        "task_id": "cve_task",
                        "task_type": "cve",
                        "latest_execute_time": 1234567890,
                        "task_result": [
                            {
                                "host_id": "id1",
                                "host_name": "",
                                "host_ip": "127.0.0.1",
                                "status": "fail",
                                "check_items": [
                                    {
                                        "item": "check network",
                                        "result": True
                                    }
                                ],
                                "cves": [
                                    {
                                        "cve_id": "cve1",
                                        "log": "",
                                        "result": "unfixed"
                                    }
                                ]
                            }
                        ]
                    }
                }
        """
        result = {}
        try:
            status_code, result = self._get_cve_task_result(data)
            LOGGER.debug("Finished getting cve task result.")
            return status_code, result
        except (ElasticsearchException, KeyError) as error:
            LOGGER.error(error)
            LOGGER.error("Getting cve task result failed due to internal error.")
            return DATABASE_QUERY_ERROR, result

    def _get_cve_task_result(self, data):
        """
        query cve task result from mysql and es.
        """
        username = data["username"]
        task_id = data["task_id"]
        cve_list = data["cve_list"]

        # task log is in the format of returned dict of func 'get_task_cve_result'
        status_code, task_log = self.get_task_ansible_info(task_id, "log", username)
        if status_code != SUCCEED:
            return status_code, {}

        task_dict = {}
        if task_log:
            task_dict = json.loads(task_log)
        if task_dict and cve_list:
            self._process_cve_task_result(task_dict, cve_list)
        return SUCCEED, {"result": task_dict}

    @staticmethod
    def _process_cve_task_result(task_dict, cve_list):
        task_result = task_dict.pop("task_result")
        filtered_result = []

        for host_result in task_result:
            all_cve_result = host_result.pop("cves")
            filtered_cve_result = []
            for cve_result in all_cve_result:
                if cve_result["cve_id"] in cve_list:
                    filtered_cve_result.append(cve_result)
            if filtered_cve_result:
                host_result["cves"] = filtered_cve_result
                filtered_result.append(host_result)

        task_dict["task_result"] = filtered_result

    def get_task_repo_result(self, data):
        """
        Get the result of each host in the task, in addition to basic info of the task.

        Args:
            data (dict): parameter. e.g.
                {
                    "username": "admin",
                    "task_id": "",
                    "host_list": []  // if empty, return all host's result
                }

        Returns:
            int: status code
            dict: query result. e.g.
                {
                    "result": {
                        "task_id": "repo_task",
                        "task_type": "repo",
                        "latest_execute_time": 1234567890,
                        "task_result": [
                            {
                                "host_id": "id1",
                                "host_name": "",
                                "host_ip": "127.0.0.1",
                                "status": "fail",
                                "check_items": [
                                    {
                                        "item": "check network",
                                        "result": True
                                    }
                                ],
                                "log": ""
                            }
                        ]
                    }
                }

        """
        result = {}
        try:
            status_code, result = self._get_repo_task_result(data)
            LOGGER.debug("Finished getting repo task result.")
            return status_code, result
        except (ElasticsearchException, KeyError) as error:
            LOGGER.error(error)
            LOGGER.error("Getting repo task result failed due to internal error.")
            return DATABASE_QUERY_ERROR, result

    def _get_repo_task_result(self, data):
        """
        query repo task result from mysql and es.
        """
        username = data["username"]
        task_id = data["task_id"]
        host_list = data["host_list"]

        # task log is in the format of returned dict of func 'get_task_cve_result'
        status_code, task_log = self.get_task_ansible_info(task_id, "log", username)
        if status_code != SUCCEED:
            return status_code, {}

        task_dict = {}
        if task_log:
            task_dict = json.loads(task_log)
        if task_dict and host_list:
            self._process_repo_task_result(task_dict, host_list)
        return SUCCEED, {"result": task_dict}

    @staticmethod
    def _process_repo_task_result(task_dict, host_list):
        task_result = task_dict.pop("task_result")
        filtered_result = []
        for host_result in task_result:
            if host_result["host_id"] in host_list:
                filtered_result.append(host_result)
        task_dict["task_result"] = filtered_result


class TaskProxy(TaskMysqlProxy, TaskEsProxy):
    def __init__(self, configuration, host=None, port=None):
        """
        Instance initialization

        Args:
            configuration (Config)
            host(str)
            port(int)
        """
        TaskMysqlProxy.__init__(self)
        TaskEsProxy.__init__(self, configuration, host, port)

    def connect(self, session):
        return TaskMysqlProxy.connect(self, session) and TaskEsProxy.connect(self)

    def close(self):
        TaskMysqlProxy.close(self)
        TaskEsProxy.close(self)

    def __del__(self):
        TaskMysqlProxy.__del__(self)
        TaskEsProxy.__del__(self)

    def generate_cve_task(self, data):
        """
        For generating, save cve task basic info to mysql, init task info in es, then return the
        basic info for generating playbook.

        Args:
            data (dict): e.g.
                {
                    "username": "admin",
                    "task_id": "",
                    "task_name": "",
                    "task_type": "",
                    "description": "",
                    "auto_reboot": True,
                    "create_time": 1,
                    "info": [
                        {
                            "cve_id": "cve1",
                            "host_info": [
                                {
                                    "host_id": "id1",
                                    "host_name": "",
                                    "host_ip": ""
                                }
                            ],
                            "reboot": True
                        }
                    ]
                }

        Returns:
            int: status code
            list: basic info after judging whether to reboot.e.g.
                [
                    {
                        "cve_id": "cve-11-11",
                        "host_info": [
                            {
                                "host_name": "name1",
                                "host_ip": "11.1.1.1",
                                "host_id": "id1"
                            }
                        ],
                        "reboot": True
                    }
                ]
        """
        result = []
        try:
            result = self._gen_cve_task(data)
            self.session.commit()
            LOGGER.debug("Finished generating cve task.")
            return SUCCEED, result
        except (SQLAlchemyError, ElasticsearchException, EsOperationError) as error:
            self.session.rollback()
            LOGGER.error(error)
            LOGGER.error("Generating cve task failed due to internal error.")
            return DATABASE_INSERT_ERROR, result

    def _gen_cve_task(self, data):
        """
        generate cve task. Process data, then:
        1. insert task basic info into mysql Task table
        2. insert host and cve's relationship and fixing status into mysql
           TaskCveHostAssociation table
        3. insert cve reboot info and fixing progress into mysql CveTaskAssociation table
        4. insert task's id and username into elasticsearch
        Args:
            data (dict): cve task info

        Returns:
            list: basic info after judging whether to reboot. (host id is popped)

        Raises:
            EsOperationError
        """
        task_id = data["task_id"]
        auto_reboot = data["auto_reboot"]
        cve_host_info = data.pop("info")

        host_set = set()
        reboot_host_set = set()
        task_cve_rows = []
        task_cve_host_rows = []

        for cve in cve_host_info:
            cve_host_set = set()
            cve_id = cve["cve_id"]
            host_num = len(cve["host_info"])
            cve["reboot"] &= auto_reboot
            task_cve_rows.append(self._task_cve_row_dict(task_id, cve_id, cve["reboot"], host_num))

            for host in cve["host_info"]:
                cve_host_set.add(host["host_id"])
                task_cve_host_rows.append(self._task_cve_host_row_dict(task_id, cve_id, host))

            host_set |= cve_host_set
            if cve["reboot"]:
                reboot_host_set |= cve_host_set

        # insert data into mysql tables
        data["host_num"] = len(host_set)
        data["need_reboot"] = len(reboot_host_set)
        self._insert_cve_task_tables(data, task_cve_rows, task_cve_host_rows)

        # insert task id and username into es
        self._init_task_in_es(task_id, data["username"])
        return cve_host_info

    def _insert_cve_task_tables(self, task_data, task_cve_rows, task_cve_host_rows):
        """
        insert data into three mysql tables when generating cve task.
        Task table need commit after add, otherwise following insertion will fail due to
        task.task_id foreign key constraint.
        Args:
            task_data (dict): task basic info for Task table
            task_cve_rows (list): list of row dict for CveTaskAssociation table
            task_cve_host_rows (list): list of row dict for TaskCveHostAssociation table

        Raises:
            SQLAlchemyError
        """
        self.session.add(Task(**task_data))
        self.session.commit()

        try:
            self.session.bulk_insert_mappings(CveTaskAssociation, task_cve_rows)
            self.session.bulk_insert_mappings(TaskCveHostAssociation, task_cve_host_rows)
        except SQLAlchemyError:
            self.session.rollback()
            self.session.query(Task).filter(Task.task_id == task_data["task_id"]).delete()
            self.session.commit()
            raise

    @staticmethod
    def _task_cve_row_dict(task_id, cve_id, reboot, host_num):
        """
        insert cve task's reboot and progress info of each cve into CveTaskAssociation table
        """
        return {"task_id": task_id, "cve_id": cve_id, "reboot": reboot, "progress": 0,
                "host_num": host_num}

    @staticmethod
    def _task_cve_host_row_dict(task_id, cve_id, host_info):
        """
        insert cve task's fixing status of each cve and host into TaskCveHostAssociation table
        """
        return {
            "task_id": task_id,
            "cve_id": cve_id,
            "host_id": host_info["host_id"],
            "host_name": host_info["host_name"],
            "public_ip": host_info["host_ip"],
            "status": "unfixed"
        }

    def _init_task_in_es(self, task_id, username):
        """
        insert task info into es. es's id (like primary key) is task's id.
        Args:
            task_id (str/None): task id
            username (str): username

        Raises:
            EsOperationError
        """
        task_body = {
            "task_id": task_id,
            "username": username,
            "playbook": "",
            "inventory": "",
            "log": ""
        }
        # assign task id as document id, make sure task id is unique
        operation_code = TaskEsProxy.insert(self, TASK_INDEX, task_body, document_id=task_id)
        if not operation_code:
            raise EsOperationError("Insert task info into elasticsearch failed.")

    def generate_repo_task(self, data):
        """
        For generating, save repo task basic info to mysql, init task info in es.

        Args:
            data (dict): e.g.
                {
                    "username": "admin"
                    "task_id": "",
                    "task_name": "",
                    "task_type": "",
                    "description": "",
                    "repo_name": "",
                    "create_time": 1,
                    "info": [
                        {
                            "host_id": "",
                            "host_name": "",
                            "host_ip": ""
                        }
                    ]
                }

        Returns:
            int: status code
        """
        try:
            self._gen_repo_task(data)
            self.session.commit()
            LOGGER.debug("Finished generating repo task.")
            return SUCCEED
        except (SQLAlchemyError, ElasticsearchException, EsOperationError) as error:
            self.session.rollback()
            LOGGER.error(error)
            LOGGER.error("Generate repo task failed due to internal error.")
            return DATABASE_INSERT_ERROR

    def _gen_repo_task(self, data):
        """
        generate repo task. Process data, then:
        1. insert task basic info into mysql Task table
        2. insert host and repo's relationship and setting status into mysql
           TaskHostRepoAssociation table
        3. insert task's id and username into elasticsearch
        Args:
            data (dict): repo task info

        Raises:
            EsOperationError
        """
        task_id = data["task_id"]
        repo_name = data.pop("repo_name")
        host_list = data.pop("info")

        task_repo_host_rows = []
        for host_info in host_list:
            task_repo_host_rows.append(self._task_repo_host_row_dict(task_id, repo_name, host_info))

        # insert data into mysql tables
        data["host_num"] = len(host_list)
        data["need_reboot"] = 0
        self._insert_repo_task_tables(data, task_repo_host_rows)

        # insert task id and username into es
        self._init_task_in_es(task_id, data["username"])

    @staticmethod
    def _task_repo_host_row_dict(task_id, repo_name, host_info):
        """
        insert repo setting into TaskHostRepoAssociation table
        """
        return {
            "task_id": task_id,
            "repo_name": repo_name,
            "host_id": host_info["host_id"],
            "host_name": host_info["host_name"],
            "public_ip": host_info["host_ip"],
            "status": "unset"
        }

    def _insert_repo_task_tables(self, task_data, task_repo_host_rows):
        """
        insert data into two tables when generating repo task.
        Task table need commit after add, otherwise following insertion will fail due to
        task.task_id foreign key constraint.
        Args:
            task_data (dict): task basic info for Task table
            task_repo_host_rows (list): list of row dict for TaskHostRepoAssociation table

        Raises:
            SQLAlchemyError
        """
        self.session.add(Task(**task_data))
        self.session.commit()

        try:
            self.session.bulk_insert_mappings(TaskHostRepoAssociation, task_repo_host_rows)
        except SQLAlchemyError:
            self.session.rollback()
            self.session.query(Task).filter(Task.task_id == task_data["task_id"]).delete()
            self.session.commit()
            raise

    def delete_task(self, data):
        """
        Delete task.

        Args:
            data (dict): parameter. e.g.
                {
                    "username": "admin",
                    "task_list": []
                }

        Returns:
            int: status code
        """
        try:
            self._delete_task(data)
            self.session.commit()
            LOGGER.debug("Finished deleting task.")
            return SUCCEED
        except (SQLAlchemyError, ElasticsearchException, EsOperationError) as error:
            self.session.rollback()
            LOGGER.error(error)
            LOGGER.error("Deleting task failed due to internal error.")
            return DATABASE_DELETE_ERROR

    def _delete_task(self, data):
        """
        Delete task's info from both mysql and es.
        Args:
            data (dict): task list info

        Raises:
            ElasticsearchException
        """
        username = data["username"]
        task_list = data["task_list"]
        deleted_task = self._delete_task_from_mysql(username, task_list)
        self._delete_task_from_es(username, deleted_task)

    def _delete_task_from_mysql(self, username, task_list):
        """
        Delete task from Task table in mysql, related rows in other tables will also be deleted.
        Args:
            username (str): user name
            task_list (list): task id list

        Returns:
            list: deleted task id list
        """
        task_query = self.session.query(Task) \
            .filter(Task.username == username, Task.task_id.in_(task_list))

        succeed_list = [row.task_id for row in task_query]
        fail_list = list(set(task_list) - set(succeed_list))

        if fail_list:
            LOGGER.debug("No data found when deleting the task '%s' from mysql." % fail_list)

        task_query.delete(synchronize_session=False)
        LOGGER.debug("Delete task from mysql succeed.")
        return succeed_list

    def _delete_task_from_es(self, username, task_list):
        """
        Delete task from elasticsearch's 'task' index
        Args:
            username (str): user name
            task_list (list): task id list

        Raises:
            EsOperationError
        """
        query_body = self._general_body()
        query_body["query"]["bool"]["must"].extend(
            [{"terms": {"_id": task_list}}, {"term": {"username": username}}])

        res = TaskEsProxy.delete(self, TASK_INDEX, query_body)
        if res:
            LOGGER.debug("Delete task from elasticsearch succeed.")
            return

        raise EsOperationError("Delete task from elasticsearch failed due to internal error.")
