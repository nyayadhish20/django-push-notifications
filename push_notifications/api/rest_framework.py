from __future__ import absolute_import

from django.db.backends.base.operations import BaseDatabaseOperations
from rest_framework import permissions
from rest_framework.serializers import ModelSerializer, ValidationError
from rest_framework.validators import UniqueValidator
from rest_framework.viewsets import ModelViewSet
from rest_framework.fields import IntegerField

from push_notifications.models import APNSDevice, GCMDevice
from push_notifications.fields import hex_re


BIGINT_MAX_VALUE = BaseDatabaseOperations.integer_field_ranges["BigIntegerField"][1]

# Fields


class HexIntegerField(IntegerField):
	"""
	Store an integer represented as a hex string of form "0x01".
	"""

	def to_internal_value(self, data):
		# validate that value is a hex number
		try:
			data = int(data, 16)
		except ValueError:
			raise ValidationError("ValidationError Device ID is not a valid hex number")
		return super(HexIntegerField, self).to_internal_value(data)

	def to_representation(self, value):
		return value


# Serializers
class DeviceSerializerMixin(ModelSerializer):
	class Meta:
		fields = ("name", "registration_id", "device_id", "active", "date_created")
		read_only_fields = ("date_created", )

		# See https://github.com/tomchristie/django-rest-framework/issues/1101
		extra_kwargs = {"active": {"default": True}}


class APNSDeviceSerializer(ModelSerializer):

	class Meta(DeviceSerializerMixin.Meta):
		model = APNSDevice

	def validate_registration_id(self, value):
		# iOS device tokens are 256-bit hexadecimal (64 characters)

		if hex_re.match(value) is None or len(value) != 64:
			raise ValidationError("Registration ID (device token) is invalid")

		return value


class GCMDeviceSerializer(ModelSerializer):
	device_id = HexIntegerField(
		help_text="ANDROID_ID / TelephonyManager.getDeviceId() (e.g: 0x01)",
		style={'input_type': 'text'},
		required=False
	)

	class Meta(DeviceSerializerMixin.Meta):
		model = GCMDevice

		extra_kwargs = {
			# Work around an issue with validating the uniqueness of
			# registration ids of up to 4k
			'registration_id': {
				'validators': [
					UniqueValidator(queryset=GCMDevice.objects.all())
				]
			}
		}

	def validate_device_id(self, value):
		# max value for django.db.models.BigIntegerField is 9223372036854775807
		# make sure the value is in valid range
		if value > BIGINT_MAX_VALUE:
			raise ValidationError("ValidationError Device ID is out of range")
		return value


# Permissions
class IsOwner(permissions.BasePermission):
	def has_object_permission(self, request, view, obj):
		# must be the owner to view the object
		return obj.user == request.user


# Mixins
class DeviceViewSetMixin(object):
	lookup_field = "registration_id"

	def perform_create(self, serializer):
		if self.request.user.is_authenticated():
			serializer.save(user=self.request.user)
		return super(DeviceViewSetMixin, self).perform_create(serializer)


class AuthorizedMixin(object):
	permission_classes = (permissions.IsAuthenticated, IsOwner)

	def get_queryset(self):
		# filter all devices to only those belonging to the current user
		return self.queryset.filter(user=self.request.user)


# ViewSets
class APNSDeviceViewSet(DeviceViewSetMixin, ModelViewSet):
	queryset = APNSDevice.objects.all()
	serializer_class = APNSDeviceSerializer


class APNSDeviceAuthorizedViewSet(AuthorizedMixin, APNSDeviceViewSet):
	pass


class GCMDeviceViewSet(DeviceViewSetMixin, ModelViewSet):
	queryset = GCMDevice.objects.all()
	serializer_class = GCMDeviceSerializer


class GCMDeviceAuthorizedViewSet(AuthorizedMixin, GCMDeviceViewSet):
	pass
