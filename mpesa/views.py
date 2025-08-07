from django.http import HttpResponse

def mpesa_home(request):
    return HttpResponse("Hello, this is a test!")
