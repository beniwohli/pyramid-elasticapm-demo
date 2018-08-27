# Copyright (c) 2018, Elasticsearch BV
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# * Redistributions of source code must retain the above copyright notice, this
#   list of conditions and the following disclaimer.
#
# * Redistributions in binary form must reproduce the above copyright notice,
#   this list of conditions and the following disclaimer in the documentation
#   and/or other materials provided with the distribution.
#
# * Neither the name of the copyright holder nor the names of its
#  contributors may be used to endorse or promote products derived from
#  this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

import pkg_resources
import sys

from pyramid.compat import reraise
from pyramid.events import ApplicationCreated, subscriber

import elasticapm
from elasticapm.utils import compat, get_url_dict


def includeme(config):
    config.add_tween('elasticapm_integration.elasticapm_tween_factory')
    config.scan('elasticapm_integration')


@subscriber(ApplicationCreated)
def elasticapm_instrument(event):
    elasticapm.instrument()


class elasticapm_tween_factory(object):
    def __init__(self, handler, registry):
        self.handler = handler
        self.registry = registry

        self.client = elasticapm.Client(
            framework_name="Pyramid",
            framework_version=pkg_resources.get_distribution("pyramid").version
        )

    def __call__(self, request):
        self.client.begin_transaction('request')
        try:
            response = self.handler(request)
            transaction_result = response.status[0] + "xx"
            elasticapm.set_context(lambda: get_data_from_response(response), "response")
            return response
        except Exception:
            transaction_result = '5xx'
            self.client.capture_exception(
                context={
                    "request": get_data_from_request(request)
                },
                handled=False,  # indicate that this exception bubbled all the way up to the user
            )
            reraise(*sys.exc_info())
        finally:
            transaction_name = request.matched_route.pattern if request.matched_route else request.view_name
            # prepend request method
            transaction_name = " ".join((request.method, transaction_name)) if transaction_name else ""
            elasticapm.set_context(lambda: get_data_from_request(request), "request")
            self.client.end_transaction(transaction_name, transaction_result)


def get_data_from_request(request):
    data = {
        "headers": dict(**request.headers),
        "method": request.method,
        "socket": {
            "remote_address": request.remote_addr,
            "encrypted": request.scheme == 'https'
        },
        "cookies": dict(**request.cookies),
        "url": get_url_dict(request.url)
    }
    # remove Cookie header since the same data is in request["cookies"] as well
    data["headers"].pop("Cookie", None)
    return data


def get_data_from_response(response):
    data = {"status_code": response.status_int}
    if response.headers:
        data["headers"] = {
            key: ";".join(response.headers.getall(key))
            for key in compat.iterkeys(response.headers)
        }
    return data