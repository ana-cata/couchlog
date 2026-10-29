from django.contrib import messages
from django.shortcuts import redirect, render

from .forms import TimeZoneForm
from .models import Profile


def home(request):
    return render(request, 'core/home.html')


def profile(request):
    profile, _ = Profile.objects.get_or_create(user=request.user)
    if request.method == 'POST':
        form = TimeZoneForm(request.POST)
        if form.is_valid():
            profile.timezone = form.cleaned_data['timezone']
            profile.save()
            messages.success(request, 'Time zone saved.')
            return redirect('profile')
    else:
        form = TimeZoneForm(initial={'timezone': profile.timezone})
    return render(request, 'core/profile.html', {'form': form, 'profile': profile})
