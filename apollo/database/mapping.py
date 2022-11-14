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
Description: Elasticsearch index related mappings
"""
from apollo.conf.constant import CVE_PKG_INDEX, TASK_INDEX

MAPPINGS = {
    TASK_INDEX: {
        "mappings": {
            "properties": {
                "task_id": {
                    "type": "keyword",
                    "ignore_above": 256
                },
                "log": {
                    "type": "text"
                },
                "username": {
                    "type": "keyword",
                    "ignore_above": 256
                }
            }
        }
    },
    CVE_PKG_INDEX: {
        "mappings": {
            "properties": {
                "cve_id": {
                    "type": "keyword",
                    "ignore_above": 256
                },
                "description": {
                    "type": "text"
                }
            }
        }
    }
}
