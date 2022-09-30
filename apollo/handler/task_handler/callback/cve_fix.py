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
Description: callback function of the cve fixing task.
"""
from apollo.handler.task_handler.callback import TaskCallback
from apollo.conf.constant import ANSIBLE_TASK_STATUS, CVE_HOST_STATUS


class CveFixCallback(TaskCallback):
    """
    Callback function for cve fixing.
    """
    def v2_runner_on_unreachable(self, result):
        host_name, task_name = self._record_info(result, ANSIBLE_TASK_STATUS.UNREACHABLE)
        self.save_to_db(task_name, host_name, CVE_HOST_STATUS.UNFIXED)

    def v2_runner_on_ok(self, result):
        host_name, task_name = self._record_info(result, ANSIBLE_TASK_STATUS.SUCCEED)
        self.save_to_db(task_name, host_name, CVE_HOST_STATUS.FIXED)

    def v2_runner_on_failed(self, result, ignore_errors=False):
        host_name, task_name = self._record_info(result, ANSIBLE_TASK_STATUS.FAIL)
        self.save_to_db(task_name, host_name, CVE_HOST_STATUS.UNFIXED)

    def save_to_db(self, cve_id, host_name, status):
        """
        When it's a check task, save the check result to member variable. 
        Otherwise update the status of the cve of the host to database.

        Args:
            cve_id (str): it corresponds to the task name in playbook.
            host_name (str)
            status (str)
        """
        # it means it's a cve fixing task.
        if self.task_info['cve'].get(cve_id) is not None:
            self.result[host_name][cve_id]['status'] = status
            host_id = self.task_info['host'][host_name]['host_id']
            self.proxy.update_cve_status(self.task_id, cve_id, host_id, status)
            self.proxy.set_cve_progress(self.task_id, [cve_id])
        else:
            self.check_result[host_name][cve_id] = self.result[host_name].pop(cve_id)
