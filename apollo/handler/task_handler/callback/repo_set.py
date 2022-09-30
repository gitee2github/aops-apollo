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
Description: callback function of the repo setting task.
"""
from apollo.handler.task_handler.callback import TaskCallback
from apollo.conf.constant import REPO_STATUS, ANSIBLE_TASK_STATUS


class RepoSetCallback(TaskCallback):
    """
    Callback function for repo setting.
    """

    def v2_runner_on_unreachable(self, result):
        host_name, task_name = self._record_info(result, ANSIBLE_TASK_STATUS.UNREACHABLE)
        self.save_to_db(task_name, host_name, REPO_STATUS.FAIL)

    def v2_runner_on_ok(self, result):
        host_name, task_name = self._record_info(result, ANSIBLE_TASK_STATUS.SUCCEED)
        self.save_to_db(task_name, host_name, REPO_STATUS.SUCCEED)

    def v2_runner_on_failed(self, result, ignore_errors=False):
        host_name, task_name = self._record_info(result, ANSIBLE_TASK_STATUS.FAIL)
        self.save_to_db(task_name, host_name, REPO_STATUS.FAIL)

    def save_to_db(self, task_name, host_name, status):
        """
        When it's a check task, save the check result to member variable.
        Otherwise update the status of the host to database.

        Args:
            task_name (str): task name in playbook.
            host_name (str)
            status (str)
        """
        # it means it's a task for setting repo.
        if task_name == 'set repo':
            self.result[host_name][task_name]['status'] = status
            host_id = self.task_info[host_name]['host_id']
            self.proxy.set_repo_status(self.task_id, [host_id], status)
            if status == REPO_STATUS.SUCCEED:
                self.proxy.set_host_repo(self.task_info[host_name]['repo_name'], [host_id])
        elif task_name.startswith('check'):
            self.check_result[host_name][task_name] = self.result[host_name].pop(
                task_name)
