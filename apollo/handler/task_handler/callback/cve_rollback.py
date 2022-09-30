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
Description: callback function of the cve rollback task.
"""
from apollo.handler.task_handler.callback.cve_fix import CveFixCallback
from apollo.conf.constant import ANSIBLE_TASK_STATUS, CVE_HOST_STATUS


class CveRollbackCallback(CveFixCallback):
    """
    Callback function for cve fixing rollback.
    """

    def v2_runner_on_unreachable(self, result):
        host_name, task_name = self._record_info(result, ANSIBLE_TASK_STATUS.UNREACHABLE)
        self.save_to_db(task_name, host_name, CVE_HOST_STATUS.FIXED)

    def v2_runner_on_ok(self, result):
        host_name, task_name = self._record_info(result, ANSIBLE_TASK_STATUS.SUCCEED)
        self.save_to_db(task_name, host_name, CVE_HOST_STATUS.UNFIXED)

    def v2_runner_on_failed(self, result, ignore_errors=False):
        host_name, task_name = self._record_info(result, ANSIBLE_TASK_STATUS.FAIL)
        self.save_to_db(task_name, host_name, CVE_HOST_STATUS.FIXED)
