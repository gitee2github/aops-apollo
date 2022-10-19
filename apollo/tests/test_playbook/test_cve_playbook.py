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

from vulcanus.compare import compare_two_object
from apollo.handler.task_handler.manager.playbook_manager import CveFixPlaybook

CHECK_ITEMS = [
    "memory",
    "repo"
]

class TestCvePlaybook(unittest.TestCase):
    def setUp(self):
        self.base_path = os.path.join(os.path.abspath(
            os.path.dirname(__file__)), 'test_file')

    def tearDown(self):
        pass

    def test_create_fix_task(self):
        cve_id = "1"
        func_param = {"test": 1}
        temp = CveFixPlaybook('1', check_items=CHECK_ITEMS).create_fix_task(cve_id, func_param)

        self.assertEqual(len(temp['tasks'][0]), 6)

    def test_create_fix_param(self):
        pb = CveFixPlaybook('1')
        package_info = {
            "a": ["b"]}
        cve_id = "a"
        param = pb.create_fix_param(cve_id, package_info)
        expected_res = {
            "shell": "yum upgrade -y --cve=a"
        }
        self.assertDictEqual(param, expected_res)

    def test_create_fix_inventory(self):
        basic_info = [
            {
                "cve_id": "cve-11-11",
                "host_info": [
                    {
                        "host_name": "a",
                        "host_ip": "ip1"
                    }
                ],
                "reboot": False
            },
            {
                "cve_id": "cve-11-12",
                "host_info": [
                    {
                        "host_name": "a",
                        "host_ip": "ip1"
                    },
                    {
                        "host_name": "b",
                        "host_ip": "ip2"
                    }
                ],
                "reboot": True
            }
        ]
        playbook = CveFixPlaybook("1", function="other")
        hosts = playbook.create_fix_inventory(basic_info)

        path = os.path.join(self.base_path, 'fix')
        with open(path, 'r', encoding='utf-8') as f:
            expected_res = yaml.safe_load(f)

        self.assertDictEqual(hosts, expected_res)

    def test_create_fix_playbook(self):
        basic_info = [
            {
                "cve_id": "cve-11-11",
                "host_info": [
                    {
                        "host_name": "a",
                        "host_ip": "ip1"
                    }
                ],
                "reboot": False
            },
            {
                "cve_id": "cve-11-12",
                "host_info": [
                    {
                        "host_name": "a",
                        "host_ip": "ip1"
                    },
                    {
                        "host_name": "b",
                        "host_ip": "ip2"
                    }
                ],
                "reboot": True
            }
        ]
        package_info = {
            "cve-11-11": ["a"],
            "cve-11-12": ["c", "b"]
        }
        path = os.path.join(self.base_path, 'fix.yml')
        with open(path, 'r', encoding='utf-8') as f:
            expected_res = yaml.safe_load(f)

        playbook = CveFixPlaybook("1", False, CHECK_ITEMS, "yum")
        pb = playbook.create_fix_playbook(basic_info, package_info)
        self.assertTrue(compare_two_object(pb, expected_res))

    def test_create_rollback_playbook(self):
        cve_list = ["cve-11-12"]
        package_info = {
            "cve-11-12": ["c", "b"]
        }
        path = os.path.join(self.base_path, 'rollback.yml')
        with open(path, 'r', encoding='utf-8') as f:
            expected_res = yaml.safe_load(f)

        playbook = CveFixPlaybook("1")
        pb, _ = playbook.create_rollback_playbook(cve_list, package_info)

        self.assertTrue(compare_two_object(expected_res, pb))
