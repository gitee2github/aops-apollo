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
from time import sleep
from copy import deepcopy
import unittest
from unittest import mock
from sqlalchemy.exc import SQLAlchemyError

from aops_utils.restful.status import SUCCEED, NO_DATA, DATABASE_INSERT_ERROR, PARTIAL_SUCCEED, \
    DATABASE_UPDATE_ERROR, SERVER_ERROR, DATABASE_QUERY_ERROR
from apollo.tests.test_database.helper import setup_mysql_db, tear_down_mysql_db, setup_es_db, \
    tear_down_es_db, SESSION
from apollo.conf import configuration
from apollo.database.proxy.task import TaskEsProxy, TaskProxy
from apollo.database.proxy.host import HostProxy
from apollo.conf.constant import ES_TEST_FLAG


class TestTaskMysqlFirst(unittest.TestCase):
    task_database = TaskProxy(configuration)
    task_database.connect(SESSION)

    @classmethod
    def setUpClass(cls):
        setup_mysql_db()

    @classmethod
    def tearDownClass(cls):
        tear_down_mysql_db()

    def test_get_scan_host_info(self):
        # query all host's info
        expected_result = [
            {
                "host_id": "id1",
                "host_name": "host1",
                "host_ip": "127.0.0.1",
                "status": "done"
            },
            {
                "host_id": "id2",
                "host_name": "host2",
                "host_ip": "127.0.0.2",
                "status": "scanning"
            }
        ]
        self.assertEqual(self.task_database.get_scan_host_info("admin", []), expected_result)

        # query one host's info
        expected_result = [
            {
                "host_id": "id2",
                "host_name": "host2",
                "host_ip": "127.0.0.2",
                "status": "scanning"
            }
        ]
        self.assertEqual(self.task_database.get_scan_host_info("admin", ["id2"]), expected_result)

    def test_init_host_scan_status(self):
        # update not exist host
        self.assertEqual(self.task_database.init_host_scan("admin", ["not_exist_id1", "id1"]), NO_DATA)

        # update exist host
        self.assertEqual(self.task_database.init_host_scan("admin", ["id1", "id2"]), SUCCEED)

        host_database = HostProxy(configuration)
        host_database.connect(SESSION)
        self.assertEqual(host_database.get_hosts_status({"host_list": ["id1", "id2"], "username": "admin"}),
                         (SUCCEED, {"result": {"id1": "scanning", "id2": "scanning"}}))

        # update all host
        # revert hosts' status
        self.task_database.update_scan_status(["id1", "id2"])
        self.assertEqual(host_database.get_hosts_status({"host_list": ["id1", "id2"], "username": "admin"}),
                         (SUCCEED, {"result": {"id1": "done", "id2": "done"}}))
        self.assertEqual(self.task_database.init_host_scan("admin", ["id1", "id2"]), SUCCEED)
        self.assertEqual(host_database.get_hosts_status({"host_list": ["id1", "id2"], "username": "admin"}),
                         (SUCCEED, {"result": {"id1": "scanning", "id2": "scanning"}}))

    def test_update_host_scan_status(self):
        # update not exist host
        self.assertEqual(self.task_database.update_scan_status(["not_exist_id1", "id1"]), NO_DATA)

        # update exist host
        self.assertEqual(self.task_database.update_scan_status(["id1", "id2"]), SUCCEED)

        host_database = HostProxy(configuration)
        host_database.connect(SESSION)
        self.assertEqual(host_database.get_hosts_status({"host_list": ["id1", "id2"], "username": "admin"}),
                         (SUCCEED, {"result": {"id1": "done", "id2": "done"}}))

    def test_get_task_list(self):
        data = {
            "sort": "create_time",
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
                    "task_id": '1111111111poiuytrewqasdfghjklmnb',
                    "task_name": "fix cve", "task_type": "cve",
                    "description": "cve task 1", "host_num": 2, "create_time": 123836139
                },
                {
                    "task_id": '2222222222poiuytrewqasdfghjklmnb',
                    "task_name": "fix cve", "task_type": "cve",
                    "description": "cve task 2", "host_num": 1, "create_time": 123836140
                },
                {
                    "task_id": 'aaaaaaaaaapoiuytrewqasdfghjklmnb',
                    "task_name": "set repo", "task_type": "repo",
                    "description": "abcd", "host_num": 1, "create_time": 123836141
                }
            ]
        }
        self.assertEqual(self.task_database.get_task_list(data), (SUCCEED, expected_query_result))

        data = {
            "sort": "create_time",
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
                    "task_id": 'aaaaaaaaaapoiuytrewqasdfghjklmnb',
                    "task_name": "set repo", "task_type": "repo",
                    "description": "abcd", "host_num": 1, "create_time": 123836141
                },
                {
                    "task_id": '2222222222poiuytrewqasdfghjklmnb',
                    "task_name": "fix cve", "task_type": "cve",
                    "description": "cve task 2", "host_num": 1, "create_time": 123836140
                },
                {
                    "task_id": '1111111111poiuytrewqasdfghjklmnb',
                    "task_name": "fix cve", "task_type": "cve",
                    "description": "cve task 1", "host_num": 2, "create_time": 123836139
                }
            ]
        }
        self.assertEqual(self.task_database.get_task_list(data), (SUCCEED, expected_query_result))

    def test_get_cve_list_filter(self):
        data = {
            "sort": "host_num",
            "direction": "asc",
            "page": 1,
            "per_page": 10,
            "username": "admin",
            "filter": {"task_type": ["repo"]}
        }
        expected_query_result = {
            "total_count": 1,
            "total_page": 1,
            "result": [
                {
                    "task_id": 'aaaaaaaaaapoiuytrewqasdfghjklmnb',
                    "task_name": "set repo", "task_type": "repo",
                    "description": "abcd", "host_num": 1, "create_time": 123836141
                }
            ]
        }
        self.assertEqual(self.task_database.get_task_list(data), (SUCCEED, expected_query_result))

    def test_get_task_progress(self):
        data = {"username": "admin",
                "task_list": ["1111111111poiuytrewqasdfghjklmnb",
                              "2222222222poiuytrewqasdfghjklmnb",
                              "aaaaaaaaaapoiuytrewqasdfghjklmnb"]}
        expected_query_result = {
            "result": {
                "1111111111poiuytrewqasdfghjklmnb": {
                    "succeed": 0,
                    "fail": 1,
                    "running": 1,
                    "unknown": 0
                },
                "2222222222poiuytrewqasdfghjklmnb": {
                    "succeed": 0,
                    "fail": 1,
                    "running": 0,
                    "unknown": 0
                },
                "aaaaaaaaaapoiuytrewqasdfghjklmnb": {
                    "succeed": 1,
                    "fail": 1,
                    "running": 0,
                    "unknown": 0
                }
            }
        }
        self.assertEqual(self.task_database.get_task_progress(data), (SUCCEED, expected_query_result))

    def test_get_task_info(self):
        data = {"username": "admin",
                "task_id": "1111111111poiuytrewqasdfghjklmnb"}
        expected_query_result = {
            "result": {
                "task_name": "fix cve",
                "description": "cve task 1",
                "host_num": 2,
                "need_reboot": 1,
                "auto_reboot": True,
                "latest_execute_time": 128467234,
            }
        }
        self.assertEqual(self.task_database.get_task_info(data), (SUCCEED, expected_query_result))

    def test_task_info_get(self):
        data = {
            "username": "admin",
            "task_id": "1111111111poiuytrewqasdfghjklmnb",
            "filter": {
                "cve_id": "qwfqwff3",
                "reboot": True,
                "status": []
            }
        }
        expected_result = {
            "total_page": 1,
            "total_count": 0,
            "result": []
        }
        self.assertEqual(self.task_database.get_cve_task_info(data), (SUCCEED, expected_result))

        data = {
            "username": "admin",
            "task_id": "1111111111poiuytrewqasdfghjklmnb",
            "filter": {
                "cve_id": "qwfqwff3",
                "reboot": False,
                "status": ["running"]
            }
        }
        expected_result = {
            "total_page": 1,
            "total_count": 1,
            "result": [{"cve_id": "qwfqwff3", "package": "ansible,tensorflow", "reboot": False,
                        "host_num": 2, "status": "running"}]
        }
        query_result = self.task_database.get_cve_task_info(data)
        sorted_pkg = sorted(query_result[1]["result"][0]["package"].split(','))
        query_result[1]["result"][0]["package"] = ','.join(sorted_pkg)
        self.assertEqual(query_result, (SUCCEED, expected_result))

        data = {
            "username": "admin",
            "task_id": "1111111111poiuytrewqasdfghjklmnb",
            "sort": "host_num",
            "direction": "desc",
            "page": 2,
            "per_page": 1,
            "filter": {
                "cve_id": "qwfqw",
                "status": ["running", "succeed"]
            }
        }
        expected_result = {
            "total_page": 2,
            "total_count": 2,
            "result": [{"cve_id": "qwfqwff4", "package": "ansible,redis", "reboot": True,
                        "host_num": 1, "status": "succeed"}]
        }
        query_result = self.task_database.get_cve_task_info(data)
        sorted_pkg = sorted(query_result[1]["result"][0]["package"].split(','))
        query_result[1]["result"][0]["package"] = ','.join(sorted_pkg)
        self.assertEqual(query_result, (SUCCEED, expected_result))

    def test_get_task_cve_status(self):
        data = {
            "username": "admin",
            "task_id": "1111111111poiuytrewqasdfghjklmnb",
            "cve_list": ["qwfqwff3"]
        }
        expected_result = {
            "result": {
                "qwfqwff3": [
                    {
                        "host_id": "id1",
                        "host_name": "host1",
                        "host_ip": "127.0.0.1",
                        "status": "running"
                    },
                    {
                        "host_id": "id2",
                        "host_name": "host2",
                        "host_ip": "127.0.0.2",
                        "status": "unfixed"
                    }
                ]
            }
        }
        query_result = self.task_database.get_task_cve_status(data)
        query_result[1]["result"]["qwfqwff3"].sort(key=lambda x: x["host_id"])
        self.assertEqual(query_result, (SUCCEED, expected_result))

        # query all cve of a task
        data = {
            "username": "admin",
            "task_id": "1111111111poiuytrewqasdfghjklmnb",
            "cve_list": []
        }
        expected_result = {
            "result": {
                "qwfqwff3": [
                    {
                        "host_id": "id1",
                        "host_name": "host1",
                        "host_ip": "127.0.0.1",
                        "status": "running"
                    },
                    {
                        "host_id": "id2",
                        "host_name": "host2",
                        "host_ip": "127.0.0.2",
                        "status": "unfixed"
                    }
                ],
                "qwfqwff4": [
                    {
                        "host_id": "id1",
                        "host_name": "host1",
                        "host_ip": "127.0.0.1",
                        "status": "fixed"
                    }
                ]
            }
        }
        query_result = self.task_database.get_task_cve_status(data)
        query_result[1]["result"]["qwfqwff3"].sort(key=lambda x: x["host_id"])
        self.assertEqual(query_result, (SUCCEED, expected_result))

        # query partial exist cve
        data = {
            "username": "admin",
            "task_id": "1111111111poiuytrewqasdfghjklmnb",
            "cve_list": ["qwfqwff3", "qwfqwff4", "not_exist_id"]
        }
        query_result = self.task_database.get_task_cve_status(data)
        query_result[1]["result"]["qwfqwff3"].sort(key=lambda x: x["host_id"])
        self.assertEqual(query_result, (PARTIAL_SUCCEED, expected_result))

    def test_get_task_cve_progress(self):
        data = {
            "username": "admin",
            "task_id": "1111111111poiuytrewqasdfghjklmnb",
            "cve_list": ["qwfqwff3"]
        }
        expected_result = {
            "result": {
                "qwfqwff3": {
                    "progress": 1,
                    "status": "running"
                }
            }
        }
        self.assertEqual(self.task_database.get_task_cve_progress(data), (SUCCEED, expected_result))

        data = {
            "username": "admin",
            "task_id": "1111111111poiuytrewqasdfghjklmnb",
            "cve_list": ["qwfqwff3", "not_exist_id"]
        }
        self.assertEqual(self.task_database.get_task_cve_progress(data), (PARTIAL_SUCCEED, expected_result))

        data = {
            "username": "admin",
            "task_id": "1111111111poiuytrewqasdfghjklmnb",
            "cve_list": ["not_exist_id"]
        }
        self.assertEqual(self.task_database.get_task_cve_progress(data), (NO_DATA, {"result": {}}))

        data = {
            "username": "admin",
            "task_id": "1111111111poiuytrewqasdfghjklmnb",
            "cve_list": []
        }
        expected_result = {
            "result": {
                "qwfqwff3": {
                    "progress": 1,
                    "status": "running"
                },
                "qwfqwff4": {
                    "progress": 1,
                    "status": "succeed"
                }
            }
        }
        self.assertEqual(self.task_database.get_task_cve_progress(data), (SUCCEED, expected_result))

    def test_get_rollback_cve_list(self):
        data = {
            "username": "admin",
            "task_id": "1111111111poiuytrewqasdfghjklmnb"
        }
        expected_result = ["qwfqwff4"]
        self.assertEqual(self.task_database.get_rollback_cve_list(data), expected_result)

    def test_get_cve_basic_info(self):
        task_id = "1111111111poiuytrewqasdfghjklmnb"
        expected_result = [
            {
                "cve_id": "qwfqwff3",
                "host_info": [{"host_id": "id1", "host_name": "host1", "host_ip": "127.0.0.1"},
                              {"host_id": "id2", "host_name": "host2", "host_ip": "127.0.0.2"}],
                "reboot": False
            },
            {
                "cve_id": "qwfqwff4",
                "host_info": [{"host_id": "id1", "host_name": "host1", "host_ip": "127.0.0.1"}],
                "reboot": True
            }
        ]
        self.assertEqual(self.task_database.get_cve_basic_info(task_id), (SUCCEED, expected_result))

        task_id = "not_exist_id"
        expected_result = []
        self.assertEqual(self.task_database.get_cve_basic_info(task_id), (NO_DATA, expected_result))

    def test_update_cve_host_status(self):
        data = {
            "task_id": "1111111111poiuytrewqasdfghjklmnb",
            "cve_id": "qwfqwff3",
            "host_id": "id1",
            "status": "fixed"
        }
        self.assertEqual(self.task_database.update_cve_status(**data), SUCCEED)

        data = {
            "task_id": "not_exist_id",
            "cve_id": "qwfqwff3",
            "host_id": "id1",
            "status": "fixed"
        }
        self.assertEqual(self.task_database.update_cve_status(**data), DATABASE_UPDATE_ERROR)


class TestTaskMysqlSecond(unittest.TestCase):
    task_database = TaskProxy(configuration)
    task_database.connect(SESSION)

    @classmethod
    def setUpClass(cls):
        setup_mysql_db()

    @classmethod
    def tearDownClass(cls):
        tear_down_mysql_db()

    def test_init_cve_task(self):
        data = {
            "task_id": "1111111111poiuytrewqasdfghjklmnb",
            "cve_list": ["qwfqwff3"]
        }
        self.assertEqual(self.task_database.init_cve_task(**data), SUCCEED)
        progress_data = {"task_id": "1111111111poiuytrewqasdfghjklmnb", "username": "admin", "cve_list": []}
        expected_progress_result = {"result": {"qwfqwff3": {"progress": 0, "status": "running"},
                                               "qwfqwff4": {"progress": 1, "status": "succeed"}}}
        self.assertEqual(self.task_database.get_task_cve_progress(progress_data), (SUCCEED, expected_progress_result))

        # test all cve
        data = {
            "task_id": "1111111111poiuytrewqasdfghjklmnb",
            "cve_list": []
        }
        self.assertEqual(self.task_database.init_cve_task(**data), SUCCEED)
        expected_progress_result = {"result": {"qwfqwff3": {"progress": 0, "status": "running"},
                                               "qwfqwff4": {"progress": 0, "status": "running"}}}
        self.assertEqual(self.task_database.get_task_cve_progress(progress_data), (SUCCEED, expected_progress_result))

    def test_set_cve_progress(self):
        # previous test case set the cve's progress to 0
        data = {
            "task_id": "1111111111poiuytrewqasdfghjklmnb",
            "cve_list": [],
            "method": "add"
        }
        progress_data = {"task_id": "1111111111poiuytrewqasdfghjklmnb", "username": "admin", "cve_list": []}
        self.assertEqual(self.task_database.set_cve_progress(**data), SUCCEED)
        expected_progress_result = {"result": {"qwfqwff3": {"progress": 1, "status": "running"},
                                               "qwfqwff4": {"progress": 1, "status": "running"}}}
        self.assertEqual(self.task_database.get_task_cve_progress(progress_data), (SUCCEED, expected_progress_result))

        data = {
            "task_id": "1111111111poiuytrewqasdfghjklmnb",
            "cve_list": [],
            "method": "fill"
        }
        self.assertEqual(self.task_database.set_cve_progress(**data), SUCCEED)
        expected_progress_result = {"result": {"qwfqwff3": {"progress": 2, "status": "running"},
                                               "qwfqwff4": {"progress": 1, "status": "running"}}}
        self.assertEqual(self.task_database.get_task_cve_progress(progress_data), (SUCCEED, expected_progress_result))

        data = {
            "task_id": "1111111111poiuytrewqasdfghjklmnb",
            "cve_list": [],
            "method": "zero"
        }
        self.assertEqual(self.task_database.set_cve_progress(**data), SUCCEED)
        expected_progress_result = {"result": {"qwfqwff3": {"progress": 0, "status": "running"},
                                               "qwfqwff4": {"progress": 0, "status": "running"}}}
        self.assertEqual(self.task_database.get_task_cve_progress(progress_data), (SUCCEED, expected_progress_result))

        data = {
            "task_id": "1111111111poiuytrewqasdfghjklmnb",
            "cve_list": ["qwfqwff3"],
            "method": "add"
        }
        self.assertEqual(self.task_database.set_cve_progress(**data), SUCCEED)
        expected_progress_result = {"result": {"qwfqwff3": {"progress": 1, "status": "running"},
                                               "qwfqwff4": {"progress": 0, "status": "running"}}}
        self.assertEqual(self.task_database.get_task_cve_progress(progress_data), (SUCCEED, expected_progress_result))

        data = {
            "task_id": "1111111111poiuytrewqasdfghjklmnb",
            "cve_list": ["qwfqwff3"],
            "method": "wrong_method"
        }
        self.assertEqual(self.task_database.set_cve_progress(**data), SERVER_ERROR)

    def test_get_repo_task_info(self):
        data = {
            "username": "admin",
            "task_id": "aaaaaaaaaapoiuytrewqasdfghjklmnb",
            "page": 1,
            "per_page": 10
        }
        data2 = deepcopy(data)
        expected_result = {
            "result": [
                {
                    "repo_name": "repo1",
                    "host_id": "id1",
                    "host_name": "host1",
                    "host_ip": "127.0.0.1",
                    "status": "set"
                },
                {
                    "repo_name": "repo2",
                    "host_id": "id2",
                    "host_name": "host2",
                    "host_ip": "127.0.0.2",
                    "status": "unset"
                }
            ],
            "total_count": 2,
            "total_page": 1
        }
        self.assertEqual(self.task_database.get_repo_task_info(data), (SUCCEED, expected_result))

        expected_result_2 = deepcopy(expected_result)
        expected_result_2["result"] = [expected_result["result"][0]]
        expected_result_2["total_count"] = 1
        data["filter"] = {"host_name": "1", "status": []}
        self.assertEqual(self.task_database.get_repo_task_info(data), (SUCCEED, expected_result_2))

        expected_result_3 = deepcopy(expected_result)
        expected_result_3["result"] = [expected_result["result"][1]]
        expected_result_3["total_count"] = 1
        data["filter"] = {"host_name": "", "status": ["unset"]}
        self.assertEqual(self.task_database.get_repo_task_info(data), (SUCCEED, expected_result_3))

        data2["per_page"] = 1
        expected_result_4 = deepcopy(expected_result)
        expected_result_4["result"] = [expected_result["result"][0]]
        expected_result_4["total_page"] = 2
        print(self.task_database.get_repo_task_info(data2))
        self.assertEqual(self.task_database.get_repo_task_info(data2), (SUCCEED, expected_result_4))

    def test_set_repo_status(self):
        data = {
            "task_id": "aaaaaaaaaapoiuytrewqasdfghjklmnb",
            "host_list": [],
            "status": "running"
        }
        self.assertEqual(self.task_database.set_repo_status(**data), SUCCEED)
        expected_info = {
            "result": [
                {
                    "repo_name": "repo1",
                    "host_id": "id1",
                    "host_name": "host1",
                    "host_ip": "127.0.0.1",
                    "status": "running"
                },
                {
                    "repo_name": "repo2",
                    "host_id": "id2",
                    "host_name": "host2",
                    "host_ip": "127.0.0.2",
                    "status": "running"
                }
            ],
            "total_count": 2,
            "total_page": 1
        }
        self.assertEqual(self.task_database.get_repo_task_info({"username": "admin",
                                                                "task_id": "aaaaaaaaaapoiuytrewqasdfghjklmnb"}),
                         (SUCCEED, expected_info))

        data = {
            "task_id": "aaaaaaaaaapoiuytrewqasdfghjklmnb",
            "host_list": ["id1"],
            "status": "set"
        }
        self.assertEqual(self.task_database.set_repo_status(**data), SUCCEED)
        expected_info = {
            "result": [
                {
                    "repo_name": "repo1",
                    "host_id": "id1",
                    "host_name": "host1",
                    "host_ip": "127.0.0.1",
                    "status": "set"
                },
                {
                    "repo_name": "repo2",
                    "host_id": "id2",
                    "host_name": "host2",
                    "host_ip": "127.0.0.2",
                    "status": "running"
                }
            ],
            "total_count": 2,
            "total_page": 1
        }
        self.assertEqual(self.task_database.get_repo_task_info({"username": "admin",
                                                                "task_id": "aaaaaaaaaapoiuytrewqasdfghjklmnb"}),
                         (SUCCEED, expected_info))

    def test_get_task_type(self):
        data = {
            "task_id": "doesn't exist id",
            "username": "admin"
        }
        self.assertEqual(self.task_database.get_task_type(**data), None)

        data = {
            "task_id": "aaaaaaaaaapoiuytrewqasdfghjklmnb",
            "username": "admin"
        }
        self.assertEqual(self.task_database.get_task_type(**data), "repo")

        data = {
            "task_id": "1111111111poiuytrewqasdfghjklmnb",
            "username": "admin"
        }
        self.assertEqual(self.task_database.get_task_type(**data), "cve")

    def test_update_execute_time(self):
        data = {
            "task_id": "1111111111poiuytrewqasdfghjklmnb",
            "username": "admin"
        }
        self.assertEqual(self.task_database.update_task_execute_time(data["task_id"], 1234567890), SUCCEED)
        changed_task_info = self.task_database.get_task_info(data)
        self.assertEqual(changed_task_info[1]["result"]["latest_execute_time"], 1234567890)

    def test_save_scan_result(self):
        host_database = HostProxy(configuration)
        host_database.connect(SESSION)
        host_data = {
            "sort": "cve_num",
            "direction": "desc",
            "page": 1,
            "per_page": 10,
            "username": "admin",
            "filter": {}
        }
        expected_host_list = {
            "total_count": 2,
            "total_page": 1,
            "result": [
                {
                    "host_id": "id2", "host_name": "host2", "host_ip": "127.0.0.2",
                    "host_group": "group1", "repo": "repo1", "cve_num": 3, "last_scan": 123836152
                },
                {
                    "host_id": "id1", "host_name": "host1", "host_ip": "127.0.0.1",
                    "host_group": "group1", "repo": "repo1", "cve_num": 2, "last_scan": 123836100
                }
            ]
        }
        self.assertEqual(host_database.get_host_list(host_data), (SUCCEED, expected_host_list))

        data = {
            "id1": [],
            "id2": ["qwfqwff4", "qwfqwff5", "qwfqwff6"],
        }
        self.assertEqual(self.task_database.save_scan_result("admin", data), SUCCEED)

        expected_host_list = {
            "total_count": 2,
            "total_page": 1,
            "result": [
                {
                    "host_id": "id2", "host_name": "host2", "host_ip": "127.0.0.2",
                    "host_group": "group1", "repo": "repo1", "cve_num": 3, "last_scan": 123836152
                },
                {
                    "host_id": "id1", "host_name": "host1", "host_ip": "127.0.0.1",
                    "host_group": "group1", "repo": "repo1", "cve_num": 0, "last_scan": 123836100
                }
            ]
        }
        self.assertEqual(host_database.get_host_list(host_data), (SUCCEED, expected_host_list))

    def test_check_task_status(self):
        result = self.task_database.check_task_status("1111111111poiuytrewqasdfghjklmnb", 'cve')
        self.assertEqual(result, False)

        result = self.task_database.check_task_status("2222222222poiuytrewqasdfghjklmnb", 'cve')
        self.assertEqual(result, True)

        result = self.task_database.check_task_status("aaaaaaaaaapoiuytrewqasdfghjklmnb", 'repo')
        self.assertEqual(result, True)


@unittest.skipUnless(ES_TEST_FLAG, "The test cases will remove all the data on es, never run on real environment.")
class TestTaskEsProxy(unittest.TestCase):
    task_database = TaskProxy(configuration)
    task_database.connect(SESSION)

    @classmethod
    def setUpClass(cls):
        setup_es_db()
        sleep(1)

    @classmethod
    def tearDownClass(cls):
        tear_down_es_db()

    def test_save_task_info(self):
        status_code = self.task_database.save_task_info("1111111111poiuytrewqasdfghjklmnb", "changed_playbook")
        self.assertEqual(status_code, SUCCEED)
        sleep(1)
        _, result = self.task_database._query_task_info_from_es("1111111111poiuytrewqasdfghjklmnb")
        result["hits"]["hits"][0]["_source"].pop("log")
        self.assertEqual(result["hits"]["hits"][0]["_source"],
                         {"task_id": "1111111111poiuytrewqasdfghjklmnb", "playbook": "changed_playbook",
                                     "inventory": "test_inventory", "username": "admin"})

        status_code = self.task_database.save_task_info("1111111111poiuytrewqasdfghjklmnb", inventory="changed_inventory")
        self.assertEqual(status_code, SUCCEED)
        sleep(1)
        _, result = self.task_database._query_task_info_from_es("1111111111poiuytrewqasdfghjklmnb")
        result["hits"]["hits"][0]["_source"].pop("log")
        self.assertEqual(result["hits"]["hits"][0]["_source"],
                         {"task_id": "1111111111poiuytrewqasdfghjklmnb", "playbook": "changed_playbook",
                                     "inventory": "changed_inventory", "username": "admin"})

        status_code = self.task_database.save_task_info("new_task", "new_playbook")
        self.assertEqual(status_code, DATABASE_INSERT_ERROR)

    def test_get_playbook(self):
        result = self.task_database.get_task_ansible_info("1111111111poiuytrewqasdfghjklmnb", "playbook")
        self.assertEqual(result, (SUCCEED, "test_playbook"))

    @mock.patch.object(TaskEsProxy, "_query_task_info_from_es")
    def test_get_playbook_error(self, mock_query):
        mock_query.return_value = (False, [])
        result = self.task_database.get_task_ansible_info("1111111111poiuytrewqasdfghjklmnb", "playbook")
        self.assertEqual(result, (DATABASE_QUERY_ERROR, ""))

    def test_get_inventory(self):
        result = self.task_database.get_task_ansible_info("1111111111poiuytrewqasdfghjklmnb", "inventory")
        self.assertEqual(result, (SUCCEED, "test_inventory"))

    @mock.patch.object(TaskEsProxy, "_query_task_info_from_es")
    def test_get_inventory_error(self, mock_query):
        mock_query.return_value = (False, [])
        result = self.task_database.get_task_ansible_info("1111111111poiuytrewqasdfghjklmnb", "inventory")
        self.assertEqual(result, (DATABASE_QUERY_ERROR, ""))

    def test_get_cve_task_result(self):
        data = {
            "username": "admin",
            "task_id": "1111111111poiuytrewqasdfghjklmnb",
            "cve_list": ["qwfqwff3"]
        }
        expected_result = {
            "task_id": "1111111111poiuytrewqasdfghjklmnb",
            "task_type": "cve",
            "latest_execute_time": 128467234,
            "task_result": [
                {
                    "host_id": "id1",
                    "host_name": "host1",
                    "host_ip": "127.0.0.1",
                    "status": "running",
                    "check_items": [
                        {
                            "item": "check network",
                            "result": True
                        }
                    ],
                    "cves": [
                        {
                            "cve_id": "qwfqwff3",
                            "log": "",
                            "result": "running"
                        }
                    ]
                },
                {
                    "host_id": "id2",
                    "host_name": "host2",
                    "host_ip": "127.0.0.2",
                    "status": "fail",
                    "check_items": [
                        {
                            "item": "check network",
                            "result": True
                        }
                    ],
                    "cves": [
                        {
                            "cve_id": "qwfqwff3",
                            "log": "",
                            "result": "unfixed"
                        }
                    ]
                }
            ]
        }
        query_result = self.task_database.get_task_cve_result(data)
        self.assertEqual(query_result, (SUCCEED, {"result": expected_result}))

    def test_get_repo_task_result(self):
        data = {
            "username": "admin",
            "task_id": "aaaaaaaaaapoiuytrewqasdfghjklmnb",
            "host_list": []
        }
        expected_result = {
            "task_id": "aaaaaaaaaapoiuytrewqasdfghjklmnb",
            "task_type": "repo",
            "latest_execute_time": 123836141,
            "task_result": [
                {
                    "host_id": "id1",
                    "host_name": "host1",
                    "host_ip": "127.0.0.1",
                    "status": "succeed",
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
        query_result = self.task_database.get_task_repo_result(data)
        self.assertEqual(query_result, (SUCCEED, {"result": expected_result}))


@unittest.skipUnless(ES_TEST_FLAG, "The test cases will remove all the data on es, never run on real environment.")
class TestTaskProxy(unittest.TestCase):
    task_database = TaskProxy(configuration)
    task_database.connect(SESSION)

    @classmethod
    def setUpClass(cls):
        setup_mysql_db()
        setup_es_db()

    @classmethod
    def tearDownClass(cls):
        tear_down_mysql_db()
        tear_down_es_db()

    def test_generate_cve_task(self):
        data = {
            "username": "admin", "task_id": "3333333333poiuytrewqasdfghjklmnb", "task_name": "fix cve added",
            "task_type": "cve", "description": "added cve task", "auto_reboot": True, "create_time": 123836144,
            "info": [
                {
                    "cve_id": "qwfqwff3",
                    "host_info": [{"host_id": "id1", "host_name": "host1", "host_ip": "127.0.0.1"},
                                  {"host_id": "id2", "host_name": "host2", "host_ip": "127.0.0.2"}],
                    "reboot": False
                },
                {
                    "cve_id": "qwfqwff4",
                    "host_info": [{"host_id": "id1", "host_name": "host1", "host_ip": "127.0.0.1"}],
                    "reboot": True
                },
                {
                    "cve_id": "qwfqwff5",
                    "host_info": [{"host_id": "id2", "host_name": "host2", "host_ip": "127.0.0.2"}],
                    "reboot": False
                }
            ]
        }
        new_data = deepcopy(data)
        expected_query_result = [
            {
                "cve_id": "qwfqwff3",
                "host_info": [{"host_id": "id1", "host_name": "host1", "host_ip": "127.0.0.1"},
                              {"host_id": "id2", "host_name": "host2", "host_ip": "127.0.0.2"}],
                "reboot": False
            },
            {
                "cve_id": "qwfqwff4",
                "host_info": [{"host_id": "id1", "host_name": "host1", "host_ip": "127.0.0.1"}],
                "reboot": True
            },
            {
                "cve_id": "qwfqwff5",
                "host_info": [{"host_id": "id2", "host_name": "host2", "host_ip": "127.0.0.2"}],
                "reboot": False
            }
        ]
        self.assertEqual(self.task_database.generate_cve_task(data), (SUCCEED, expected_query_result))

        new_data["task_id"] = "4444444444poiuytrewqasdfghjklmnb"
        new_data["create_time"] = 123836145
        new_data["auto_reboot"] = False
        expected_query_result[1]["reboot"] = False
        self.assertEqual(self.task_database.generate_cve_task(new_data), (SUCCEED, expected_query_result))

    @mock.patch.object(TaskProxy, "_insert_cve_task_tables")
    def test_generate_cve_task_error(self, mock_insert):
        mock_insert.side_effect = SQLAlchemyError("mock a SQLAlchemyError.")
        data = {
            "username": "admin", "task_id": "1111", "task_name": "task 2", "task_type": "cve",
            "description": "task 2 description", "auto_reboot": True, "create_time": 1,
            "info": [
                {
                    "cve_id": "qwfqwff3",
                    "host_info": [{"host_id": "id1", "host_name": "host1", "host_ip": "127.0.0.1"},
                                  {"host_id": "id2", "host_name": "host2", "host_ip": "127.0.0.2"}],
                    "reboot": False
                },
                {
                    "cve_id": "qwfqwff4",
                    "host_info": [{"host_id": "id1", "host_name": "host1", "host_ip": "127.0.0.1"}],
                    "reboot": True
                },
                {
                    "cve_id": "qwfqwff5",
                    "host_info": [{"host_id": "id2", "host_name": "host2", "host_ip": "127.0.0.2"}],
                    "reboot": False
                }
            ]
        }
        self.assertEqual(self.task_database.generate_cve_task(data), (DATABASE_INSERT_ERROR, []))

    def test_gen_repo_task(self):
        data = {
            "username": "admin",
            "task_id": "bbbbbbbbbbpoiuytrewqasdfghjklmnb",
            "task_name": "added repo task",
            "task_type": "repo",
            "description": "added repo task desc",
            "repo_name": "aaa repo",
            "create_time": 123836146,
            "info": [{"host_id": "id1", "host_name": "host1", "host_ip": "127.0.0.1"},
                     {"host_id": "id2", "host_name": "host2", "host_ip": "127.0.0.2"}]
        }
        self.assertEqual(self.task_database.generate_repo_task(data), SUCCEED)
        expected_task_info = {
            "result": {
                "task_name": "added repo task",
                "description": "added repo task desc",
                "host_num": 2,
                "need_reboot": 0,
                "auto_reboot": False,
                "latest_execute_time": None
            }
        }
        self.assertEqual(self.task_database.get_task_info({"username": "admin",
                                                           "task_id": "bbbbbbbbbbpoiuytrewqasdfghjklmnb"}),
                         (SUCCEED, expected_task_info))
        expected_repo_task_info = {
            "result": [
                {
                    "repo_name": "aaa repo",
                    "host_id": "id1",
                    "host_name": "host1",
                    "host_ip": "127.0.0.1",
                    "status": "unset"
                },
                {
                    "repo_name": "aaa repo",
                    "host_id": "id2",
                    "host_name": "host2",
                    "host_ip": "127.0.0.2",
                    "status": "unset"
                }
            ],
            "total_count": 2,
            "total_page": 1
        }
        self.assertEqual(self.task_database.get_repo_task_info({"username": "admin",
                                                                "task_id": "bbbbbbbbbbpoiuytrewqasdfghjklmnb"}),
                         (SUCCEED, expected_repo_task_info))

    @mock.patch.object(TaskProxy, "_insert_repo_task_tables")
    def test_generate_repo_task_error(self, mock_insert):
        mock_insert.side_effect = SQLAlchemyError("mock a SQLAlchemyError.")
        data = {
            "username": "admin",
            "task_id": "ccccccccccpoiuytrewqasdfghjklmnb",
            "task_name": "added repo task",
            "task_type": "repo",
            "description": "added repo task desc",
            "repo_name": "aaa repo",
            "create_time": 123836146,
            "info": [{"host_id": "id1", "host_name": "host1", "host_ip": "127.0.0.1"},
                     {"host_id": "id2", "host_name": "host2", "host_ip": "127.0.0.2"}]
        }
        self.assertEqual(self.task_database.generate_repo_task(data), DATABASE_INSERT_ERROR)
        self.assertEqual(self.task_database.get_task_info({"username": "admin",
                                                           "task_id": "ccccccccccpoiuytrewqasdfghjklmnb"}),
                         (NO_DATA, {"result": {}}))

    def test_z_delete(self):
        result = self.task_database.delete_task({"task_list": ["1111111111poiuytrewqasdfghjklmnb"], "username": "admin"})
        self.assertEqual(result, SUCCEED)
        sleep(1)
        query_result = self.task_database.get_task_info({"task_id": "1111111111poiuytrewqasdfghjklmnb", "username": "admin"})
        self.assertEqual(query_result, (NO_DATA, {"result": {}}))
        inventory_result = self.task_database.get_task_ansible_info("1111111111poiuytrewqasdfghjklmnb", "inventory")
        self.assertEqual(inventory_result, (NO_DATA, ""))
