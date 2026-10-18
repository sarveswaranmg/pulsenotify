from django.contrib.auth import get_user_model
from rest_framework import serializers
from .models import PriceAlert

User = get_user_model()

class RegisterSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(write_only=True, min_length=8, trim_whitespace=False)
    email = serializers.EmailField(required=False, allow_blank=True)

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("A user with that username already exists.")
        return value

    def create(self, validated_data):
        # Role is deliberately not accepted from client input.
        return User.objects.create_user(
            username=validated_data["username"],
            password=validated_data["password"],
            email=validated_data.get("email", ""),
        )


class PriceAlertSerializer(serializers.ModelSerializer):
    class Meta:
        model = PriceAlert
        fields = ("id", "origin", "destination", "threshold_price", "status", "created_at")
        read_only_fields = ("id", "status", "created_at")

    def validate_origin(self, value):
        value = value.strip().upper()
        if not value.isalpha() or len(value) != 3:
            raise serializers.ValidationError("Origin must be a three-letter airport code.")
        return value

    def validate_destination(self, value):
        value = value.strip().upper()
        if not value.isalpha() or len(value) != 3:
            raise serializers.ValidationError("Destination must be a three-letter airport code.")
        return value

    def validate(self, attrs):
        if attrs.get("origin") == attrs.get("destination"):
            raise serializers.ValidationError("Origin and destination must be different.")
        return attrs
