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
import time
import json
from abc import ABC, abstractmethod

from aops_utils.log.log import LOGGER
from apollo.conf.constant import ANSIBLE_TASK_STATUS
from apollo.handler.task_handler.config import INVENTORY_DIR, PLAYBOOK_DIR


class Manager(ABC):
    """
    Base manager, define execute steps and handle function of each step.
    """

    def __init__(self, proxy, task_id, task_info):
        """
        Args:
            proxy (object): database proxy instance
            task_id (str): id of current task
            task_info (dict): task info, it's generally host info.
        """
        self.proxy = proxy
        self.task_id = task_id
        self.task_info = task_info
        self.task = None
        self.inventory_path = os.path.join(INVENTORY_DIR, self.task_id)
        self.playbook_path = os.path.join(PLAYBOOK_DIR, self.task_id + '.yml')
        self.cur_time = int(time.time())

    @abstractmethod
    def pre_handle(self):
        """
        Pre handle before executing the task, it's often about initing some status.
        """

    @abstractmethod
    def handle(self):
        """
        Task executing, it's often an ansible playbook executing.
        """

    @abstractmethod
    def post_handle(self):
        """
        Post handle after executing the task, which is generally result parsing.
        """

    @abstractmethod
    def fault_handle(self):
        """
        Handle function when trap into fault, it's often used to fix the status.
        """

    def execute_task(self):
        """
        Run task according to the two handle function steps.
        """
        self.handle()
        self.post_handle()

    @staticmethod
    def _record_check_info(info, res):
        """
        Record check info, set status to fail if one of the check item failed.

        Args:
            info (dict): check result
            res (dict): record result
        """
        if not info:
            return

        for check_item_name, check_info in info.items():
            if check_info['status'] != ANSIBLE_TASK_STATUS.SUCCEED:
                res['status'] = 'fail'
                check_item_result = False
            else:
                check_item_result = True
            res['check_items'].append(
                {"item": check_item_name, "result": check_item_result})

    def _save_result(self, task_result, task_type):
        """
        Save the result to database.

        Args:
            task_result (list)
            task_type (str)
        """
        result = {
            "task_id": self.task_id,
            "task_type": task_type,
            "latest_execute_time": self.cur_time,
            "task_result": task_result
        }
        LOGGER.debug(result)
        self.proxy.save_task_info(self.task_id, log=json.dumps(result))
