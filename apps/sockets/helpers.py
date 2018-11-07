# coding=UTF8
from collections import OrderedDict

from yaml.composer import Composer
from yaml.constructor import SafeConstructor
from yaml.parser import Parser
from yaml.reader import Reader
from yaml.resolver import Resolver
from yaml.scanner import Scanner

from apps.core.helpers import add_post_transaction_success_operation
from apps.data.models import Klass
from apps.data.tasks import KlassOperationQueue
from apps.instances.helpers import get_current_instance


"""
A PyYAML loader that annotates position in source code.
The loader is based on `SafeConstructor`, i.e., the behaviour of
`yaml.safe_load`, but in addition:
 - Every dict/list/unicode is replaced with dict_node/list_node/unicode_node,
   which subclasses dict/list/unicode to add the attributes `start_mark`
   and `end_mark`. (See the yaml.error module for the `Mark` class.)
"""


def create_node_class(base_cls):
    class NodeClass(base_cls):
        def __new__(cls, val=None, *args, **kwargs):
            return super().__new__(cls, val)

        def __init__(self, val=None, start_mark=None, end_mark=None):
            if base_cls != str and val is not None:
                super().__init__(val)
            self.start_mark = start_mark
            self.end_mark = end_mark

        @property
        def line(self):
            return self.start_mark.line + 1

    NodeClass.__name__ = '%s_node' % base_cls.__name__
    return NodeClass


dict_node = create_node_class(OrderedDict)
list_node = create_node_class(list)
unicode_node = create_node_class(str)


class NodeConstructor(SafeConstructor):
    # To support lazy loading, the original constructors first yield
    # an empty object, then fill them in when iterated. Due to
    # laziness we omit this behaviour (and will only do "deep
    # construction") by first exhausting iterators, then yielding
    # copies.
    def construct_yaml_map(self, node):
        obj, = SafeConstructor.construct_yaml_map(self, node)
        return dict_node(obj, node.start_mark, node.end_mark)

    def construct_yaml_seq(self, node):
        obj, = SafeConstructor.construct_yaml_seq(self, node)
        return list_node(obj, node.start_mark, node.end_mark)

    def construct_yaml_str(self, node):
        obj = SafeConstructor.construct_scalar(self, node)
        return unicode_node(obj, node.start_mark, node.end_mark)


NodeConstructor.add_constructor(
    'tag:yaml.org,2002:map',
    NodeConstructor.construct_yaml_map)

NodeConstructor.add_constructor(
    'tag:yaml.org,2002:seq',
    NodeConstructor.construct_yaml_seq)

NodeConstructor.add_constructor(
    'tag:yaml.org,2002:str',
    NodeConstructor.construct_yaml_str)


class MarkedLoader(Reader, Scanner, Parser, Composer, NodeConstructor, Resolver):
    def __init__(self, stream):
        Reader.__init__(self, stream)
        Scanner.__init__(self)
        Parser.__init__(self)
        Composer.__init__(self)
        SafeConstructor.__init__(self)
        Resolver.__init__(self)


def marked_load(stream):
    return MarkedLoader(stream).get_single_data()


def unref_data_klass(socket_pk, klass_name, field_dict, using=None):
    try:
        klass = Klass.objects.select_for_update().get(name=klass_name)
    except Klass.DoesNotExist:
        return

    if 'managed_by' in klass.refs and socket_pk in klass.refs['managed_by']:
        klass.refs['managed_by'].remove(socket_pk)

    field_refs = klass.refs.get('fields', {})
    field_props = klass.refs.get('props', {})
    for field_name in field_dict.keys():
        # Cleanup field refs
        if field_name in field_refs and socket_pk in field_refs[field_name]:
            field_refs[field_name].remove(socket_pk)

        # Cleanup field props refs
        for prop, prop_sockets in list(field_props.get(field_name, {}).items()):
            if socket_pk in prop_sockets:
                prop_sockets.remove(socket_pk)

    cleanup_data_klass_ref(klass, save=True, using=using)


def cleanup_data_klass_ref(klass, save=False, using=None):
    # If klass is no longer managed by any socket, delete it.
    if 'managed_by' in klass.refs and not klass.refs['managed_by']:
        if klass.is_locked:
            add_post_transaction_success_operation(
                KlassOperationQueue.delay,
                using=using, instance_pk=get_current_instance().pk, klass_pk=klass.pk, op='delete')
        else:
            klass.delete()
        return

    if klass.is_locked:
        add_post_transaction_success_operation(
            KlassOperationQueue.delay, using=using, instance_pk=get_current_instance().pk, klass_pk=klass.pk,
            op='cleanup_refs')
        return

    klass.cleanup_refs(save=save)
