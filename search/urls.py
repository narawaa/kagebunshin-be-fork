from django.urls import path
from search.views import get_data

app_name = 'search'
urlpatterns = [
    path('get-data/', get_data, name='get_example_data'),
]
