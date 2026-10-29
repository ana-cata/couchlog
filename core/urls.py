from django.contrib.auth import views as auth_views
from django.urls import path, register_converter

from . import views


class KindConverter:
    """Lets an address say which kind of title it is: only 'movie' or 'series'."""

    regex = 'movie|series'

    def to_python(self, value):
        return value

    def to_url(self, value):
        return value


register_converter(KindConverter, 'kind')

urlpatterns = [
    path('', views.home, name='home'),
    path('search/', views.search, name='search'),
    path('<kind:kind>/<int:tmdb_id>/', views.title, name='title'),
    path('about/', views.about, name='about'),
    path('profile/', views.profile, name='profile'),
    path('login/', auth_views.LoginView.as_view(template_name='core/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
]
