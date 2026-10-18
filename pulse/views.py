import random
import requests
from decimal import Decimal
from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .models import NotificationLog, PriceAlert, UserProfile
from .permissions import IsAdminUser
from .price_logic import should_trigger_alert
from .serializers import PriceAlertSerializer, RegisterSerializer

User = get_user_model()

MOCK_PRICES = {
    "DEL-BOM": (3000, 7000),
    "BLR-HYD": (1500, 4000),
    "DEL-BLR": (4000, 9000),
    "BOM-GOA": (2000, 5000),
}


class RegisterView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        token = RefreshToken.for_user(user)
        return Response({
            "username": user.username,
            "access": str(token.access_token),
            "role": user.profile.role,
        }, status=status.HTTP_201_CREATED)


class LoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        username = request.data.get("username", "")
        password = request.data.get("password", "")
        user = authenticate(request=request, username=username, password=password)
        if user is None:
            return Response({"detail": "Invalid username or password."}, status=status.HTTP_401_UNAUTHORIZED)
        token = RefreshToken.for_user(user)
        return Response({
            "username": user.username,
            "access": str(token.access_token),
            "role": user.profile.role,
        }, status=status.HTTP_200_OK)


class AlertListCreateView(generics.ListCreateAPIView):
    serializer_class = PriceAlertSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return PriceAlert.objects.filter(user=self.request.user).order_by("-created_at")

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class AlertDeactivateView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, pk):
        alert = get_object_or_404(PriceAlert, pk=pk)
        if alert.user_id != request.user.id:
            # Don't disclose whether another user's alert exists.
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        alert.status = PriceAlert.Status.INACTIVE
        alert.save(update_fields=["status"])
        return Response({"status": "inactive"}, status=status.HTTP_200_OK)


def flight_price(request):
    route = request.GET.get("route", "").strip().upper()
    price_range = MOCK_PRICES.get(route)
    if not price_range:
        return JsonResponse({"error": "Route not found"}, status=404)
    return JsonResponse({"route": route, "price": random.randint(*price_range)})


class AdminSummaryView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUser]

    def get(self, request):
        alert_stats = PriceAlert.objects.aggregate(
            total_alerts=Count("id"),
            active_alerts=Count("id", filter=Q(status=PriceAlert.Status.ACTIVE)),
            triggered_alerts=Count("id", filter=Q(status=PriceAlert.Status.TRIGGERED)),
        )
        notification_stats = NotificationLog.objects.aggregate(total_notifications=Count("id"))
        top_routes = list(
            PriceAlert.objects.values("origin", "destination")
            .annotate(alert_count=Count("id"))
            .order_by("-alert_count", "origin", "destination")[:5]
        )
        for route in top_routes:
            route["route"] = f'{route.pop("origin")}-{route.pop("destination")}'
        return Response({
            **alert_stats,
            **notification_stats,
            "top_routes": top_routes,
        })


# Exposed for focused unit testing; production task uses this same business rule.
def price_meets_threshold(current_price, threshold_price):
    return should_trigger_alert(Decimal(str(current_price)), Decimal(str(threshold_price)))
