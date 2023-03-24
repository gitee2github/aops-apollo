#!/usr/bin/python3
# ******************************************************************************
# Copyright (c) Huawei Technologies Co., Ltd. 2021-2021. All rights reserved.
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
import datetime
import time

from apollo.conf import configuration
from apollo.conf.constant import TIMED_TASK_CONFIG_PATH
from apollo.cron import TimedTaskBase
from apollo.cron.manager import get_timed_task_config_info
from apollo.database import session_maker
from apollo.database.proxy.task import TaskProxy
from vulcanus.log.log import LOGGER


class TimedCorrectTask(TimedTaskBase):
    """
    Timed correct data tasks
    """
    config_info = get_timed_task_config_info(TIMED_TASK_CONFIG_PATH)
    SERVICE_TIMEOUT_THRESHOLD_MIN = config_info.get("correct_data").get("service_timeout_threshold_min")

    @staticmethod
    def task_enter():
        """
        Start the correct after the specified time of day.
        """
        LOGGER.info("Begin to correct the whole host in %s.", str(datetime.datetime.now()))
        proxy = TaskProxy(configuration)
        if not proxy.connect(session_maker()):
            LOGGER.error("Connect to database fail, return.")

        abnormal_task_list = TimedCorrectTask.get_abnormal_task(proxy)
        if abnormal_task_list:
            proxy.update_task_status(abnormal_task_list)
        else:
            LOGGER.debug("No data needs to be corrected")

    @staticmethod
    def get_abnormal_task(proxy: TaskProxy):
        """
        Get abnormal tasks based on set thresholds and task creation time

        Args:
            proxy: Connected database proxy.

        Returns:
            list: The element of each list is the task ID
        """
        running_task_list = proxy.get_task_create_time()

        abnormal_task_list = []
        current_time = int(time.time())
        for task_id, task_type, create_time in running_task_list:
            if current_time - int(create_time) >= TimedCorrectTask.SERVICE_TIMEOUT_THRESHOLD_MIN * 60:
                abnormal_task_list.append(task_id)

        return abnormal_task_list


