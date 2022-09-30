#!/usr/bin/python3
# ******************************************************************************
# Copyright (c) Huawei Technologies Co., Ltd. 2021-2022. All rights reserved.
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
from unittest import mock

from apollo.conf.constant import REPO_STATUS, ANSIBLE_TASK_STATUS
from apollo.handler.task_handler.callback.repo_set import RepoSetCallback
from apollo.database.proxy.task import TaskMysqlProxy
from apollo.tests.test_callback import Host, Test


class TestCveRollbackCallback(unittest.TestCase):
    def setUp(self):
        task_info = {
            "name1": {
                "host_id": "id1",
                "repo_name": "a"
            },
            "name2": {
                "host_id": "id2",
                "repo_Name": "c"
            },
            "name3": {
                "host_id": "id3",
                "repo_name": "b"
            }
        }
        proxy = TaskMysqlProxy()
        self.call = RepoSetCallback('1', proxy, task_info)

    def tearDown(self):
        pass

    @mock.patch.object(TaskMysqlProxy, 'set_host_repo')
    @mock.patch.object(TaskMysqlProxy, 'set_repo_status')
    def test_result(self, mock_set_repo_status, mock_set_host_repo):
        result1 = Test(Host('name1'), {'stdout': "11"}, "check1")
        self.call.v2_runner_on_ok(result1)

        result2 = Test(Host('name1'), {'msg': "222"}, "set repo")
        self.call.v2_runner_on_unreachable(result2)

        result3 = Test(Host('name2'), {'stdout': "12"}, "check1")
        self.call.v2_runner_on_ok(result3)

        result4 = Test(Host('name2'), {'stderr': "13"}, "set repo")
        self.call.v2_runner_on_failed(result4)
        
        result5 = Test(Host('name3'), {'stdout': "12"}, "check1")
        self.call.v2_runner_on_ok(result5)

        result6 = Test(Host('name3'), {'stdout': "13"}, "set repo")
        self.call.v2_runner_on_ok(result6)

        expected_res = {
            "name1": {
                "set repo": {
                    "info": "222",
                    "status": REPO_STATUS.FAIL
                }
            },
            "name2": {
                "set repo": {
                    "info": "13",
                    "status": REPO_STATUS.FAIL
                }
            },
            "name3": {
                "set repo": {
                    "info": "13",
                    "status": REPO_STATUS.SUCCEED
                }
            }
        }
        expected_check_res = {
            "name1": {
                "check1": {
                    "info": "11",
                    "status": ANSIBLE_TASK_STATUS.SUCCEED
                }
            },
            "name2": {
                "check1": {
                    "info": "12",
                    "status": ANSIBLE_TASK_STATUS.SUCCEED
                }
            },
            "name3": {
                "check1": {
                    "info": "12",
                    "status": ANSIBLE_TASK_STATUS.SUCCEED
                }
            }
        }
        self.assertDictEqual(expected_res, self.call.result)
        self.assertDictEqual(expected_check_res, self.call.check_result)
        mock_set_host_repo.assert_called_with('b', ['id3'])
