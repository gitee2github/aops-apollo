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
import shutil
from unittest import mock

from vulcanus.compare import compare_two_object
from vulcanus.restful.status import DATABASE_CONNECT_ERROR, NO_DATA, SUCCEED, WRONG_DATA
from apollo.handler.task_handler.config import REPO_DIR
from apollo.handler.task_handler.manager.playbook_manager import RepoPlaybook
from apollo.database.proxy.repo import RepoProxy

CHECK_ITEMS = [
    "memory"
]


class TestRepoPlaybook(unittest.TestCase):
    def setUp(self):
        self.base_path = os.path.join(os.path.abspath(
            os.path.dirname(__file__)), 'test_file')
        self.pb = RepoPlaybook('1', False, CHECK_ITEMS)
        self.username = 'test111'
        self.repo_name = 'test'
        self.repo_dir = os.path.join(REPO_DIR, self.username)
        if os.path.exists(self.repo_dir):
            shutil.rmtree(self.repo_dir)

    def tearDown(self):
        if os.path.exists(self.repo_dir):
            shutil.rmtree(self.repo_dir)

    def test_create_repo_playbook(self):
        self.pb.repo_path = "/etc/yum.repos.d/openEuler.repo"
        playbook = self.pb.create_playbook()
        path = os.path.join(self.base_path, 'repo.yml')
        with open(path, 'r', encoding='utf-8') as f:
            expected_res = yaml.safe_load(f)

        self.assertTrue(compare_two_object(expected_res, playbook))

    def test_check_repo_data(self):
        repo_info = {
            "repo": "aa"
        }
        res = self.pb.check_repo_data(self.repo_name, self.username, repo_info)
        self.assertEqual(res, False)
    
        # test local file
        repo_path = os.path.join(
            self.repo_dir, '{}.repo'.format(self.repo_name))

        repo_info['repo_data'] = "aa"
        res = self.pb.check_repo_data(self.repo_name, self.username, repo_info)

        self.assertEqual(res, True)
        with open(repo_path, 'r') as f:
            content = f.read()
        self.assertEqual(content, 'aa')


    @mock.patch.object(RepoPlaybook, 'check_repo_data')
    @mock.patch.object(RepoPlaybook, 'check_repo_attr')
    @mock.patch.object(RepoProxy, 'get_repo')
    @mock.patch.object(RepoProxy, 'connect')
    def test_check_repo(self, mock_connect, mock_get_repo, mock_check_attr, mock_check_data):
        host_info = []
        mock_connect.return_value = False
        res = self.pb.check_repo(self.repo_name, self.username, host_info)
        self.assertEqual(res, DATABASE_CONNECT_ERROR)

        mock_connect.return_value = True
        mock_get_repo.return_value = 1, []
        res = self.pb.check_repo(self.repo_name, self.username, host_info)
        self.assertEqual(res, 1)

        mock_get_repo.return_value = SUCCEED, {"result": ["a", "b"]}
        res = self.pb.check_repo(self.repo_name, self.username, host_info)
        self.assertEqual(res, WRONG_DATA)

        mock_get_repo.return_value = SUCCEED, {"result": ["a"]}
        mock_check_attr.return_value = True
        mock_check_data.return_value = False
        res = self.pb.check_repo(self.repo_name, self.username, host_info)
        self.assertEqual(res, NO_DATA)

        mock_check_data.return_value = True
        res = self.pb.check_repo(self.repo_name, self.username, host_info)
        self.assertEqual(res, SUCCEED)
