import pytest

from nameko.events import event_handler, EventHandler
from nameko.extensions import DependencyProvider, Entrypoint
from nameko.rpc import rpc, Rpc
from nameko.testing.services import entrypoint_hook, dummy
from nameko.testing.utils import get_extension
from nameko.utils import get_redacted_args, REDACTED


redacted = {}


@pytest.fixture(autouse=True)
def reset():
    redacted.clear()


class Logger(DependencyProvider):
    """ Example DependencyProvider that makes use of ``get_redacted_args``
    to redact ``sensitive_variables`` on entrypoints.
    """

    def worker_setup(self, worker_ctx):
        entrypoint = worker_ctx.entrypoint
        args = worker_ctx.args
        kwargs = worker_ctx.kwargs

        redacted.update(get_redacted_args(entrypoint, *args, **kwargs))


class Service(object):
    name = "service"

    logger = Logger()

    @event_handler("service", "event_type",
                   sensitive_variables="event_data.foo")
    def handle(self, event_data):
        pass

    @rpc(sensitive_variables=("a", "b.x[0]", "b.x[2]"))
    def method(self, a, b, c):
        return [a, b, c]

    @dummy(sensitive_variables=("foo",))
    def stub(self, foo, bar):
        pass


def test_sensitive_rpc(container_factory, rabbit_config):

    container = container_factory(Service, rabbit_config)
    rpc_entrypoint = get_extension(container, Rpc)

    assert rpc_entrypoint.sensitive_variables == ("a", "b.x[0]", "b.x[2]")

    a = "A"
    b = {'x': [1, 2, 3], 'y': [4, 5, 6]}
    c = "C"

    with entrypoint_hook(container, "method") as method:
        assert method(a, b, c) == [a, b, c]

    assert redacted == {
        'a': REDACTED,
        'b': {
            'x': [REDACTED, 2, REDACTED],
            'y': [4, 5, 6]
        },
        'c': 'C'
    }


def test_sensitive_event(container_factory, rabbit_config):

    container = container_factory(Service, rabbit_config)
    handler_entrypoint = get_extension(container, EventHandler)

    assert handler_entrypoint.sensitive_variables == "event_data.foo"

    with entrypoint_hook(container, "handle") as handler:
        handler({'foo': 'FOO', 'bar': 'BAR'})

    assert redacted == {
        'event_data': {
            'foo': REDACTED,
            'bar': 'BAR'
        }
    }


def test_sensitive_generic_entrypoint(container_factory, rabbit_config):

    container = container_factory(Service, rabbit_config)
    dummy_entrypoint = get_extension(container, Entrypoint, method_name="stub")

    assert dummy_entrypoint.sensitive_variables == ("foo",)

    with entrypoint_hook(container, "stub") as stub:
        stub("FOO", "BAR")

    assert redacted == {
        'foo': REDACTED,
        'bar': 'BAR'
    }
