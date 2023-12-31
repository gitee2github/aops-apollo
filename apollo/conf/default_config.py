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
Description: default config of apollo
"""
apollo = {
    "IP": "127.0.0.1",
    "PORT": 11116,
    "HOST_VAULT_DIR": "/opt/aops",
}

cve = {"CVE_FIX_FUNCTION": "yum", "CVE_SCAN_TIME": 2}

mysql = {
    "IP": "127.0.0.1",
    "PORT": 3306,
    "DATABASE_NAME": "aops",
    "ENGINE_FORMAT": "mysql+pymysql://@%s:%s/%s",
    "POOL_SIZE": 100,
    "POOL_RECYCLE": 7200,
}

elasticsearch = {"IP": "127.0.0.1", "PORT": 9200, "MAX_ES_QUERY_NUM": 10000000}

zeus = {"IP": "127.0.0.1", "PORT": 11111}

redis = {"IP": "127.0.0.1", "PORT": 6379}

hermes = {"IP": "127.0.0.1", "PORT": 8000}
