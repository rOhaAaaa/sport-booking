from django.contrib.auth import authenticate, login, logout
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from rest_framework import generics, status
from rest_framework.authentication import SessionAuthentication
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import UserProfile
from .serializers import (
    LoginSerializer,
    RegistrationSerializer,
    UserProfileSerializer,
)


class CSRFTokenView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({
            "csrfToken": get_token(request),
        })


@method_decorator(csrf_protect, name="dispatch")
class RegistrationView(generics.CreateAPIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    serializer_class = RegistrationSerializer
    http_method_names = ["post", "options"]


@method_decorator(csrf_protect, name="dispatch")
class LoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = authenticate(
            request=request._request,
            username=serializer.validated_data["username"],
            password=serializer.validated_data["password"],
        )

        if user is None:
            return Response(
                {
                    "detail": (
                        "Неправильне ім’я користувача або пароль."
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        login(request._request, user)

        return Response({
            "detail": "Вхід виконано успішно.",
            "username": user.username,
            "csrfToken": get_token(request),
        })


@method_decorator(csrf_protect, name="dispatch")
class LogoutView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        logout(request._request)

        return Response({
            "detail": "Вихід виконано успішно.",
        })


@method_decorator(csrf_protect, name="dispatch")
class OwnProfileView(generics.RetrieveUpdateAPIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]
    serializer_class = UserProfileSerializer
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    http_method_names = ["get", "patch", "head", "options"]

    def get_object(self):
        profile, _ = UserProfile.objects.get_or_create(
            user=self.request.user,
        )
        self.check_object_permissions(self.request, profile)
        return profile