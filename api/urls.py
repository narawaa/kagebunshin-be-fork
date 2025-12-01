from django.urls import path
from api.views import test_sparql

app_name = 'api'
urlpatterns = [
    path('test-sparql/', test_sparql, name='test_sparql'),
]
