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
Description: Self-defined Exception class
"""


class ParseAdvisoryError(Exception):
    """
    Something went wrong when parsing security advisory xml file, raise the error
    """
    def __init__(self, error_info=''):
        super().__init__(self)
        self.message = error_info

    def __str__(self):
        return self.message


class EsOperationError(Exception):
    """
    When operate es, the operation code is False, raise the error
    """
    def __init__(self, error_info=''):
        super().__init__(self)
        self.message = error_info

    def __str__(self):
        return self.message
