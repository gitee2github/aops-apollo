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
Description:
"""
import unittest

from vulcanus.restful.status import PARTIAL_SUCCEED, SUCCEED, NO_DATA
from apollo.database.proxy.cve import CveProxy
from apollo.database.table import CveUserAssociation
from apollo.tests.test_database.helper import setup_mysql_db, tear_down_mysql_db, setup_es_db, \
    tear_down_es_db, SESSION
from apollo.conf import configuration
from apollo.conf.constant import ES_TEST_FLAG


class TestCveMysqlProxy(unittest.TestCase):
    cve_database = CveProxy(configuration)
    cve_database.connect(SESSION)

    @classmethod
    def setUpClass(cls):
        setup_mysql_db()

    @classmethod
    def tearDownClass(cls):
        tear_down_mysql_db()

    def test_get_overview(self):
        data = {"username": "admin"}
        expected_query_result = {
            "result": {
                "Critical": 0, "High": 1, "Medium": 1, "Low": 1, "Unknown": 1
            }
        }
        self.assertEqual(self.cve_database.get_cve_overview(data), (SUCCEED, expected_query_result))

    def test_get_cve_host(self):
        data = {"cve_id": "qwfqwff4", "username": "admin", "sort": "last_scan"}
        expected_query_result = {
            "total_count": 2, "total_page": 1,
            "result": [
                {"host_id": "id1", "host_name": "host1",
                 "host_ip": "127.0.0.1",
                 "host_group": "group1", "repo": "repo1", "last_scan": 123836100
                 },
                {"host_id": "id2", "host_name": "host2",
                 "host_ip": "127.0.0.2",
                 "host_group": "group1", "repo": "repo1", "last_scan": 123836152
                 }
            ]
        }
        self.assertEqual(self.cve_database.get_cve_host(data), (SUCCEED, expected_query_result))

        data = {"cve_id": "qwfqwff6", "username": "admin"}
        expected_query_result = {"total_count": 0, "total_page": 1, "result": []}
        self.assertEqual(self.cve_database.get_cve_host(data), (SUCCEED, expected_query_result))

        data = {"cve_id": "not_exist_id", "username": "admin"}
        expected_query_result = {"total_count": 0, "total_page": 1, "result": []}
        self.assertEqual(self.cve_database.get_cve_host(data), (SUCCEED, expected_query_result))

    def test_get_cve_task_host(self):
        data = {"cve_list": ["qwfqwff5"], "username": "admin"}
        expected_query_result = {
            "result": {
                "qwfqwff5": [{"host_id": "id2", "host_name": "host2", "host_ip": "127.0.0.2"}]
            }
        }
        self.assertEqual(self.cve_database.get_cve_task_hosts(data), (SUCCEED, expected_query_result))

        data = {"cve_list": ["qwfqwff5", "qwfqwff6", "not_exist_id"], "username": "admin"}
        expected_query_result = {
            "result": {
                "qwfqwff5": [{"host_id": "id2", "host_name": "host2", "host_ip": "127.0.0.2"}]
            }
        }
        self.assertEqual(self.cve_database.get_cve_task_hosts(data), (PARTIAL_SUCCEED, expected_query_result))

        data = {"cve_list": ["not_exist_id"], "username": "admin"}
        self.assertEqual(self.cve_database.get_cve_task_hosts(data), (NO_DATA, {"result": {}}))

    def test_set_cve_status(self):
        data = {"cve_list": ["qwfqwff4", "qwfqwff5", "not_exist_id"], "username": "admin", "status": "on-hold"}
        self.assertEqual(self.cve_database.set_cve_status(data), NO_DATA)

        data = {"cve_list": ["not_exist_id"], "username": "admin", "status": "on-hold"}
        self.assertEqual(self.cve_database.set_cve_status(data), NO_DATA)

        data = {"cve_list": ["qwfqwff4", "qwfqwff5"], "username": "admin", "status": "on-hold"}
        self.assertEqual(self.cve_database.set_cve_status(data), SUCCEED)

        status_1 = self.cve_database.session.query(CveUserAssociation). \
            filter(CveUserAssociation.username == "admin", CveUserAssociation.cve_id == "qwfqwff4"). \
            one().status
        self.assertEqual("on-hold", status_1)

        status_2 = self.cve_database.session.query(CveUserAssociation). \
            filter(CveUserAssociation.username == "admin", CveUserAssociation.cve_id == "qwfqwff5"). \
            one().status
        self.assertEqual("on-hold", status_2)

    def test_get_cve_action(self):
        data = {"cve_list": ["qwfqwff3", "qwfqwff4", "not_exist_id"], "username": "admin"}
        expected_query_result = {
            "result": {
                "qwfqwff3": {"reboot": False, "package": "ansible,tensorflow"},
                "qwfqwff4": {"reboot": True, "package": "ansible,redis"}
            }
        }
        query_result = self.cve_database.get_cve_action(data)
        sorted_pkg = sorted(query_result[1]["result"]["qwfqwff3"]["package"].split(','))
        query_result[1]["result"]["qwfqwff3"]["package"] = ','.join(sorted_pkg)
        sorted_pkg = sorted(query_result[1]["result"]["qwfqwff4"]["package"].split(','))
        query_result[1]["result"]["qwfqwff4"]["package"] = ','.join(sorted_pkg)
        self.assertEqual(self.cve_database.get_cve_action(data), (PARTIAL_SUCCEED, expected_query_result))

        data = {"cve_list": ["not_exist_id"], "username": "admin"}
        self.assertEqual(self.cve_database.get_cve_action(data), (NO_DATA, {"result": {}}))


@unittest.skipUnless(ES_TEST_FLAG, "The test cases will remove all the data on es, never run on real environment.")
class TestCveProxy(unittest.TestCase):
    cve_database = CveProxy(configuration)
    cve_database.connect(SESSION)

    @classmethod
    def setUpClass(cls):
        setup_mysql_db()
        setup_es_db()

    @classmethod
    def tearDownClass(cls):
        tear_down_mysql_db()
        tear_down_es_db()

    def test_get_cve_list_sort(self):
        data = {
            "sort": "host_num",
            "direction": "asc",
            "page": 1,
            "per_page": 10,
            "username": "admin",
            "filter": {}
        }
        expected_query_result = {
            "total_count": 3,
            "total_page": 1,
            "result": [
                {
                    "cve_id": 'qwfqwff5', "publish_time": "111", "severity": "Low",
                    "description": "abc", "cvss_score": "3", "status": "not reviewed",
                    "host_num": 1
                },
                {
                    "cve_id": 'qwfqwff3', "publish_time": "qwff", "severity": "High",
                    "description": "asdqwfqwf", "cvss_score": "7.2", "status": "in review",
                    "host_num": 2
                },
                {
                    "cve_id": 'qwfqwff4', "publish_time": "asyubdqsd", "severity": "Medium",
                    "description": "sef", "cvss_score": "3", "status": "not reviewed",
                    "host_num": 2
                }
            ]
        }
        result = self.cve_database.get_cve_list(data)
        # get rid of random sequence when two cve's host num are equal
        result[1]["result"].pop(-1)
        result[1]["result"].pop(-1)
        expected_query_result["result"].pop(-1)
        expected_query_result["result"].pop(-1)
        self.assertEqual(result, (SUCCEED, expected_query_result))

        data = {
            "sort": "host_num",
            "direction": "desc",
            "page": 1,
            "per_page": 10,
            "username": "admin",
            "filter": {}
        }
        expected_query_result = {
            "total_count": 3,
            "total_page": 1,
            "result": [
                {
                    "cve_id": 'qwfqwff3', "publish_time": "qwff", "severity": "High",
                    "description": "asdqwfqwf", "cvss_score": "7.2", "status": "in review",
                    "host_num": 2
                },
                {
                    "cve_id": 'qwfqwff4', "publish_time": "asyubdqsd", "severity": "Medium",
                    "description": "sef", "cvss_score": "3", "status": "not reviewed",
                    "host_num": 2
                },
                {
                    "cve_id": 'qwfqwff5', "publish_time": "111", "severity": "Low",
                    "description": "abc", "cvss_score": "3", "status": "not reviewed",
                    "host_num": 1
                }
            ]
        }
        result = self.cve_database.get_cve_list(data)
        # get rid of random sequence when two cve's host num are equal
        result[1]["result"].pop(0)
        result[1]["result"].pop(0)
        expected_query_result["result"].pop(0)
        expected_query_result["result"].pop(0)
        self.assertEqual(result, (SUCCEED, expected_query_result))

    def test_get_cve_list_filter(self):
        data = {
            "sort": "host_num",
            "direction": "asc",
            "page": 1,
            "per_page": 10,
            "username": "admin",
            "filter": {"status": ["in review"]}
        }
        expected_query_result = {
            "total_count": 1,
            "total_page": 1,
            "result": [
                {
                    "cve_id": 'qwfqwff3', "publish_time": "qwff", "severity": "High",
                    "description": "asdqwfqwf", "cvss_score": "7.2", "status": "in review",
                    "host_num": 2
                }
            ]
        }
        self.assertEqual(self.cve_database.get_cve_list(data), (SUCCEED, expected_query_result))

    def test_get_cve_info(self):
        data = {"cve_id": "qwfqwff4", "username": "admin"}
        expected_query_result = {
            "result": {
                "cve_id": "qwfqwff4", "publish_time": "asyubdqsd",
                "severity": "Medium", "description": "sef", "cvss_score": "3",
                "status": "not reviewed", "package": "ansible,redis",
                "related_cve": ["qwfqwff3", "qwfqwff6"]
            }
        }
        query_result = self.cve_database.get_cve_info(data)
        query_result[1]["result"]["related_cve"].sort()
        sorted_pkg = sorted(query_result[1]["result"]["package"].split(','))
        query_result[1]["result"]["package"] = ','.join(sorted_pkg)
        self.assertEqual(query_result, (SUCCEED, expected_query_result))

        data = {"cve_id": "qwfqwff5", "username": "admin"}
        expected_query_result = {
            "result": {
                "cve_id": "qwfqwff5", "publish_time": "111",
                "severity": "Low", "description": "abc", "cvss_score": "3",
                "status": "not reviewed", "package": "", "related_cve": []
            }
        }
        self.assertEqual(self.cve_database.get_cve_info(data), (SUCCEED, expected_query_result))

        data = {"cve_id": "not_exist_id", "username": "admin"}
        self.assertEqual(self.cve_database.get_cve_info(data), (NO_DATA, {"result": {}}))
