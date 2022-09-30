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

from apollo.handler.task_handler.callback.cve_scan import CveScanCallback
from apollo.database.proxy.task import TaskMysqlProxy
from apollo.tests.test_callback import Host, Test


class TestCveScanCallback(unittest.TestCase):
    def setUp(self):
        task_info = [
            {
                "host_name": "name1",
                "host_id": "id1",
                "host_ip": "ip1"
            },
            {
                "host_name": "name2",
                "host_id": "id2",
                "host_ip": "ip2"
            },
            {
                "host_name": "name3",
                "host_id": "id3",
                "host_ip": "ip3"
            }
        ]
        proxy = TaskMysqlProxy()
        self.call = CveScanCallback('1', proxy, task_info)

    def tearDown(self):
        pass

    @mock.patch.object(TaskMysqlProxy, 'update_scan_status')
    def test_result(self, mock_update_scan_status):
        result1 = Test(Host('name1'), {'msg': "11"}, "scan")
        self.call.v2_runner_on_unreachable(result1)

        result2 = Test(Host('name2'), {'stdout': "12"}, "scan")
        self.call.v2_runner_on_ok(result2)

        result3 = Test(Host('name3'), {'stderr': "13"}, "scan")
        self.call.v2_runner_on_failed(result3)

        self.assertEqual(mock_update_scan_status.call_count, 3)
