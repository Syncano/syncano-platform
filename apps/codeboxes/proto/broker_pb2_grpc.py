# Generated by the gRPC Python protocol compiler plugin. DO NOT EDIT!
import grpc

from . import broker_pb2 as pkg_dot_broker_dot_proto_dot_broker__pb2


class ScriptRunnerStub(object):
    # missing associated documentation comment in .proto file
    pass

    def __init__(self, channel):
        """Constructor.

        Args:
          channel: A grpc.Channel.
        """
        self.Run = channel.unary_unary(
            '/broker.ScriptRunner/Run',
            request_serializer=pkg_dot_broker_dot_proto_dot_broker__pb2.RunRequest.SerializeToString,
            response_deserializer=pkg_dot_broker_dot_proto_dot_broker__pb2.RunResponse.FromString,
        )


class ScriptRunnerServicer(object):
    # missing associated documentation comment in .proto file
    pass

    def Run(self, request, context):
        """Run runs script in secure environment.
        """
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')


def add_ScriptRunnerServicer_to_server(servicer, server):
    rpc_method_handlers = {
        'Run': grpc.unary_unary_rpc_method_handler(
            servicer.Run,
            request_deserializer=pkg_dot_broker_dot_proto_dot_broker__pb2.RunRequest.FromString,
            response_serializer=pkg_dot_broker_dot_proto_dot_broker__pb2.RunResponse.SerializeToString,
        ),
    }
    generic_handler = grpc.method_handlers_generic_handler(
        'broker.ScriptRunner', rpc_method_handlers)
    server.add_generic_rpc_handlers((generic_handler,))
