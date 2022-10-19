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
import os
import json
import unittest
from unittest import mock
from collections import namedtuple

from vulcanus.restful.status import SUCCEED
from apollo.handler.task_handler.manager.cve_fix_manager import CveFixManager
from apollo.handler.task_handler.manager.task_manager import CveAnsible
from apollo.handler.task_handler.config import PLAYBOOK_DIR
from apollo.conf import configuration
from apollo.database.proxy.task import TaskProxy
from apollo.conf.constant import CVE_HOST_STATUS, ANSIBLE_TASK_STATUS


class TestCveFixManager(unittest.TestCase):
    def setUp(self):
        proxy = TaskProxy(configuration)
        self.manager = CveFixManager(proxy, 'a', 'a')
        self.manager.cur_time = 22

    def tearDown(self):
        pass

    def test_pre_handle(self):
        with mock.patch.object(TaskProxy, 'init_cve_task') as mock_init_status:
            mock_init_status.return_value = 1
            res = self.manager.pre_handle()
            self.assertEqual(res, False)

        with mock.patch.object(TaskProxy, 'init_cve_task') as mock_init_status:
            mock_init_status.return_value = SUCCEED
            with mock.patch.object(TaskProxy, 'update_task_execute_time') as mock_update:
                mock_update.return_value = SUCCEED
                res = self.manager.pre_handle()
                self.assertEqual(res, True)

    def test_handle(self):
        path = os.path.join(PLAYBOOK_DIR, 'a' + '.yml')
        with mock.patch.object(CveAnsible, 'playbook') as mock_pb:
            mock_pb.return_value = True
            self.manager.handle()
            mock_pb.assert_called_with([path])

    @mock.patch.object(TaskProxy, 'fix_task_status')
    @mock.patch.object(TaskProxy, 'save_task_info')
    @mock.patch.object(TaskProxy, 'set_cve_progress')
    def test_post_handle(self, mock_set_progress, mock_save_result, mock_fix_status):
        mock_set_progress.return_value = 1
        task = namedtuple('task', ['result', 'check', 'info'])
        task.result = {
            "name1": {
                "cve1": {
                    "status": CVE_HOST_STATUS.UNFIXED,
                    "info": "1"
                },
                "cve2": {
                    "status": CVE_HOST_STATUS.FIXED,
                    "info": "2"
                }
            },
            "name2": {}
        }
        task.check = {
            "name1": {
                "check1": {
                    "status": ANSIBLE_TASK_STATUS.SUCCEED
                },
                "check2": {
                    "status": ANSIBLE_TASK_STATUS.SUCCEED
                }
            },
            "name2": {
                "check1": {
                    "status": ANSIBLE_TASK_STATUS.FAIL
                },
                "check2": {
                    "status": ANSIBLE_TASK_STATUS.SUCCEED
                }
            }
        }
        task.info = {
            "host": {
                "name1": {
                    "host_id": "id1",
                    "host_name": "name1",
                    "host_ip": "ip1",
                    "cve": {
                        "cve1": 1,
                        "cve2": 1
                    }
                },
                "name2": {
                    "host_id": "id2",
                    "host_name": "name2",
                    "host_ip": "ip2",
                    "cve": {
                        "cve1": 1,
                        "cve2": 2
                    }
                }
            }
        }
        expected_res = {
            "task_id": "a",
            "task_type": "cve",
            "latest_execute_time": 22,
            "task_result": [
                {
                    "host_id": "id1",
                    "host_name": "name1",
                    "host_ip": "ip1",
                    "status": "fail",
                    "check_items": [
                        {
                            "item": "check1",
                            "result": True
                        },
                        {
                            "item": "check2",
                            "result": True
                        }
                    ],
                    "cves": [
                        {
                            "cve_id": "cve1",
                            "log": "1",
                            "result": CVE_HOST_STATUS.UNFIXED
                        },
                        {
                            "cve_id": "cve2",
                            "log": "2",
                            "result": CVE_HOST_STATUS.FIXED
                        }
                    ]
                },
                {
                    "host_id": "id2",
                    "host_name": "name2",
                    "host_ip": "ip2",
                    "status": "fail",
                    "check_items": [
                        {
                            "item": "check1",
                            "result": False
                        },
                        {
                            "item": "check2",
                            "result": True
                        }
                    ],
                    "cves": [
                        {
                            "cve_id": "cve1",
                            "log": "",
                            "result": CVE_HOST_STATUS.UNKNOWN
                        },
                        {
                            "cve_id": "cve2",
                            "log": "",
                            "result": CVE_HOST_STATUS.UNKNOWN
                        }
                    ]
                }
            ]
        }
        self.manager.task = task
        self.manager.post_handle()
        mock_save_result.assert_called_with('a', log=json.dumps(expected_res))
