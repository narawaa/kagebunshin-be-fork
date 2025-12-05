from django.urls import path
from search.views import *

app_name = 'search'
urlpatterns = [
    path('get-data/', get_data, name='get_example_data'),

    path('anime/', get_anime, name='get_anime'),
    path('anime/theme/', get_anime_by_theme, name='get_anime_by_theme'),
    path('character/', get_character, name='get_character'),

    path('anime/query/', query_anime, name='query_anime'),
    path('character/query/', query_character, name='query_character'),
]
