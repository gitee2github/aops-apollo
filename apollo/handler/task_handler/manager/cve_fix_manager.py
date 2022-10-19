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
Description: Task manager for cve fixing
"""
from vulcanus.log.log import LOGGER
from vulcanus.restful.status import SUCCEED
from apollo.conf.constant import CVE_HOST_STATUS
from apollo.handler.task_handler.manager import Manager
from apollo.handler.task_handler.manager.task_manager import CveAnsible
from apollo.handler.task_handler.callback.cve_fix import CveFixCallback


class CveFixManager(Manager):
    """
    Manager for cve fixing
    """

    def pre_handle(self):
        """
        Init host status to 'running', and update latest task execute time.

        Returns:
            bool
        """
        if self.proxy.init_cve_task(self.task_id, []) != SUCCEED:
            LOGGER.error(
                "Init the host status in database failed, stop cve fixing task %s.", self.task_id)
            return False

        if self.proxy.update_task_execute_time(self.task_id, self.cur_time) != SUCCEED:
            LOGGER.warning(
                "Update latest execute time for cve fix task %s failed.", self.task_id)

        return True

    def handle(self):
        """
        Executing cve fix task.
        """
        LOGGER.info("Cve fixing task %s start to execute.", self.task_id)
        self.task = CveAnsible(inventory=self.inventory_path,
                               callback=CveFixCallback(self.task_id, self.proxy, self.task_info))
        self.task.playbook([self.playbook_path])
        LOGGER.info(
            "Cve fixing task %s end, begin to handle result.", self.task_id)

    def post_handle(self):
        """
        After executing the task, parse the checking and executing result, then
        save to database.
        """
        LOGGER.debug(self.task.result)
        LOGGER.debug(self.task.check)
        LOGGER.debug(self.task.info)
        task_result = []
        for host_name, host_info in self.task.info['host'].items():
            temp = {
                "host_id": host_info['host_id'],
                "host_name": host_name,
                "host_ip": host_info['host_ip'],
                "status": "succeed",
                "check_items": [],
                "cves": []
            }

            self._record_check_info(self.task.check.get(host_name), temp)
            self._record_fix_info(
                self.task.result.get(host_name), temp, host_info)

            task_result.append(temp)

        self._save_result(task_result, "cve")
        self.fault_handle()

    def fault_handle(self):
        """
        When the task is completed or execute fail, fill the progress and set the
        host status to 'unknown'.
        """
        self.proxy.set_cve_progress(self.task_id, [], 'fill')
        self.proxy.fix_task_status(self.task_id, 'cve')

    @staticmethod
    def _record_fix_info(info, res, host_info):
        """
        Record cve fixing info, set status to fail if one of the task failed.

        Args:
            info (dict): task result
            res (dict): data record
            host_info (dict): host info including cve info
        """
        cve_info = host_info['cve']
        for cve_id in cve_info.keys():
            fix_info = info.get(cve_id)
            # the fix status of the cve is unknown
            if fix_info is None:
                res['status'] = 'fail'
                log = ""
                fix_result = CVE_HOST_STATUS.UNKNOWN
            else:
                log = fix_info['info']
                fix_result = fix_info['status']
                if fix_result == CVE_HOST_STATUS.UNFIXED:
                    res['status'] = 'fail'
            res['cves'].append(
                {"cve_id": cve_id, "log": log, "result": fix_result})
