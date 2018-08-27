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