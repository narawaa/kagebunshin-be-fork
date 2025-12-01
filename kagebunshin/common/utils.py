from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler
from rest_framework import status

def api_response(status_code, message, data=None):
    if data is None:
        data = []
    return Response({
        "status": status_code,
        "message": message,
        "data": data
    }, status=status_code)

def custom_exception_handler(exc, context):
    response = drf_exception_handler(exc, context)

    if response is not None:
        try:
            response_data = dict(response.data)
            message = response_data.pop('detail', 'Terjadi kesalahan.')
            return api_response(
                status_code=response.status_code,
                message=message,
                data=response_data
            )
        except Exception as e:
            return api_response(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                message='Terjadi kesalahan pada sistem.',
                data={'error': str(e)}
            )

    return api_response(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        message='Terjadi kesalahan internal.',
        data={}
    )