from django import forms

from utils.api import serializers, UsernameSerializer
from contest.serializers import ContestSerializer, UserContestSerializer

from .models import AdminType, ProblemPermission, User, UserProfile
from lecture.models import signup_class
from contest.models import Contest
from lecture.serializers import LectureSerializer


class UserLoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField()
    tfa_code = serializers.CharField(required=False, allow_blank=True)


class UsernameOrEmailCheckSerializer(serializers.Serializer):
    username = serializers.CharField(required=False)
    email = serializers.EmailField(required=False)
    phonenum = serializers.CharField(required=False)


class UserRegisterSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=32)
    realname = serializers.CharField(max_length=32)
    password = serializers.CharField(min_length=6)
    email = serializers.EmailField(max_length=64)
    phonemum = serializers.CharField(min_length=8)
    captcha = serializers.CharField()


class UserChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField()
    new_password = serializers.CharField(min_length=6)
    tfa_code = serializers.CharField(required=False, allow_blank=True)


class UserChangeEmailSerializer(serializers.Serializer):
    password = serializers.CharField()
    new_email = serializers.EmailField(max_length=64)
    tfa_code = serializers.CharField(required=False, allow_blank=True)


class GenerateUserSerializer(serializers.Serializer):
    prefix = serializers.CharField(max_length=16, allow_blank=True)
    suffix = serializers.CharField(max_length=16, allow_blank=True)
    number_from = serializers.IntegerField()
    number_to = serializers.IntegerField()
    password_length = serializers.IntegerField(max_value=16, default=8)


class ImportUserSeralizer(serializers.Serializer):
    users = serializers.ListField(
        child=serializers.ListField(child=serializers.CharField(max_length=64)))


class UserAdminSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = "__all__"

    def get_real_name(self, obj):
        return obj.userprofile.real_name

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "realname", "username", "email", "admin_type", "problem_permission",
                  "create_time", "last_login", "two_factor_auth", "open_api", "is_disabled"]

class SimpleSignupSerializer(serializers.ModelSerializer):
    user = UserSerializer()
    class Meta:
        model = signup_class
        fields = "__all__"

class ContestSignupSerializer(serializers.ModelSerializer):
    totalScore = serializers.IntegerField()
    lecDict = serializers.DictField()

    class Meta:
        model = signup_class
        fields = "__all__"

######################################################
class SignupSerializer(serializers.ModelSerializer):
    user = UserSerializer()
    lecture = LectureSerializer()
    totalPractice = serializers.IntegerField()
    subPractice = serializers.IntegerField()
    solvePractice = serializers.IntegerField()
    totalAssign = serializers.IntegerField()
    subAssign = serializers.IntegerField()
    solveAssign = serializers.IntegerField()
    totalProblem = serializers.IntegerField() # 시리얼라이저에 변수 명, 데이터형 명시하여 값을 전달할 수 있음
    solveProblem = serializers.IntegerField()
    tryProblem = serializers.IntegerField()
    totalScore = serializers.IntegerField()
    maxScore = serializers.IntegerField()
    avgScore = serializers.FloatField()
    progress = serializers.FloatField()
    lecDict = serializers.DictField()
    class Meta:
        model = signup_class
        fields = "__all__"

class MainSignupSerializer(SignupSerializer):
    contestlist = serializers.DictField()

class UserProfileSerializer(serializers.ModelSerializer):
    user = UserSerializer()
    real_name = serializers.SerializerMethodField()

    class Meta:
        model = UserProfile
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        self.show_real_name = kwargs.pop("show_real_name", False)
        super(UserProfileSerializer, self).__init__(*args, **kwargs)

    def get_real_name(self, obj):
        return obj.real_name if self.show_real_name else None


class EditUserSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    username = serializers.CharField(max_length=32)
    realname = serializers.CharField(max_length=32, allow_blank=True, allow_null=True)
    password = serializers.CharField(min_length=6, allow_blank=True, required=False, default=None)
    email = serializers.EmailField(max_length=64)
    admin_type = serializers.ChoiceField(choices=(AdminType.REGULAR_USER, AdminType.ADMIN, AdminType.TA_ADMIN, AdminType.SUPER_ADMIN))
    problem_permission = serializers.ChoiceField(choices=(ProblemPermission.NONE, ProblemPermission.OWN,
                                                          ProblemPermission.SEMI, ProblemPermission.ALL))
    open_api = serializers.BooleanField()
    two_factor_auth = serializers.BooleanField()
    is_disabled = serializers.BooleanField()


class EditUserProfileSerializer(serializers.Serializer):
    realname = serializers.CharField(max_length=32, allow_null=True, required=False)
    #real_name = serializers.CharField(max_length=32, allow_null=True, required=False)
    # avatar = serializers.CharField(max_length=256, allow_blank=True, required=False)
    # blog = serializers.URLField(max_length=256, allow_blank=True, required=False)
    # mood = serializers.CharField(max_length=256, allow_blank=True, required=False)
    # github = serializers.CharField(max_length=64, allow_blank=True, required=False)
    # school = serializers.CharField(max_length=64, allow_blank=True, required=False)
    phonenum = serializers.CharField(max_length=64, allow_blank=True, required=False)
    # major = serializers.CharField(max_length=64, allow_blank=True, required=False)
    # language = serializers.CharField(max_length=32, allow_blank=True, required=False)


class ApplyResetPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()
    captcha = serializers.CharField()


class ResetPasswordSerializer(serializers.Serializer):
    token = serializers.CharField()
    password = serializers.CharField(min_length=6)
    captcha = serializers.CharField()


class SSOSerializer(serializers.Serializer):
    token = serializers.CharField()


class TwoFactorAuthCodeSerializer(serializers.Serializer):
    code = serializers.IntegerField()


class ImageUploadForm(forms.Form):
    image = forms.FileField()


class FileUploadForm(forms.Form):
    file = forms.FileField()


class RankInfoSerializer(serializers.ModelSerializer):
    user = UsernameSerializer()

    class Meta:
        model = UserProfile
        fields = "__all__"
