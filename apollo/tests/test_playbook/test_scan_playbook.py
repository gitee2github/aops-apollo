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
from apollo.handler.task_handler.manager.playbook_manager import CveScanPlaybook


class TestCveScanPlaybook(unittest.TestCase):
    def setUp(self):
        self.base_path = os.path.join(os.path.abspath(
            os.path.dirname(__file__)), 'test_file')
        self.pb = CveScanPlaybook('1', False)

    def tearDown(self):
        pass

    def test_create_repo_playbook(self):
        playbook = self.pb.create_playbook()
        path = os.path.join(self.base_path, 'scan.yml')
        with open(path, 'r', encoding='utf-8') as f:
            expected_res = yaml.safe_load(f)

        self.assertTrue(compare_two_object(expected_res, playbook))
