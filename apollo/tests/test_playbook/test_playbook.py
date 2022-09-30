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
import unittest
import yaml

from aops_utils.compare import compare_two_object
from apollo.handler.task_handler.manager.playbook_manager import Playbook


class TestPlaybook(unittest.TestCase):
    def setUp(self):
        self.base_path = os.path.join(os.path.abspath(
            os.path.dirname(__file__)), 'test_file')
        self.pb = Playbook('1', False, ["a"])

    def tearDown(self):
        pass
    
    def test_create_check_task(self):
        pb = self.pb.create_check_task({"a": 1})
        expected_res = [
            {
                "a": 1
            },
            {
                "hosts": "total_hosts",
                "gather_facts": False,
                "tasks": [
                    {
                        'name': 'check a',
                        'become': True,
                        'become_user': 'root',
                        'shell': 'sh /tmp/check.sh a',
                        'register': 'check_a_result',
                        'ignore_errors': True
                    }
                ]
            }
        ]
        self.assertEqual(pb, expected_res)

    def test_create_inventory(self):
        info = [
            {
                "host_id": "id1",
                "host_name": "a",
                "host_ip": "ip1"
            },
            {
                "host_id": "id2",
                "host_name": "b",
                "host_ip": "ip2"
            }
        ]
        inventory = self.pb.create_inventory(info)
        path = os.path.join(self.base_path, 'scan')
        with open(path, 'r', encoding='utf-8') as f:
            expected_res = yaml.safe_load(f)

        self.assertDictEqual(expected_res, inventory)
