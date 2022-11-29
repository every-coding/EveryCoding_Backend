import os
import re
import xlsxwriter

from django.db import transaction, IntegrityError
from django.db.models import Q
from django.http import HttpResponse
from django.contrib.auth.hashers import make_password

from contest.models import Contest, OIContestRank
from lecture.views.LectureAnalysis import LectureAnalysis, DataType, ContestType, lecDispatcher
from lecture.views.LectureBuilder import LectureBuilder
from submission.models import Submission
from utils.api import APIView, validate_serializer
from utils.shortcuts import rand_str
from lecture.models import signup_class
from problem.models import Problem

from ..decorators import super_admin_required
from lecture.models import ta_admin_class
from ..models import AdminType, ProblemPermission, User, UserProfile
from ..serializers import EditUserSerializer, UserAdminSerializer, GenerateUserSerializer, UserSerializer, \
    SimpleSignupSerializer, ContestSignupSerializer
from ..serializers import ImportUserSeralizer, SignupSerializer
from django.db.models import Max
from lecture.views.stdResult import RefLecture, SubmitLecture

class PublicContInfoAPI(APIView):
    def get(self, request):
        """
        :param request:
        :return:
        """
        user_id = request.GET.get("id")

        lecture_id = request.GET.get("lectureid")
        contest_id = request.GET.get("contest_id")

        if contest_id:
            contest = Contest.objects.get(id=contest_id)
            problems = Problem.objects.filter(contest=contest).order_by("-create_time")
            prob_dict = dict()
            for prob in problems:
                prob_dict[prob._id] = 0

            OIContestRK = OIContestRank.objects.filter(contest=contest,
                                                       user__is_disabled=False). \
                select_related("user").order_by("user.realname")
            try:
                ulist = signup_class.objects.filter(contest__id=contest_id).select_related('contest').order_by(
                    "realname")  # lecture_signup_class 테이블의 모든 값, 외래키가 있는 lecture 테이블의 값을 가져온다
                ulist = ulist.exclude(user__admin_type__in=[AdminType.ADMIN, AdminType.SUPER_ADMIN])

            except signup_class.DoesNotExist:
                return self.error("수강중인 학생이 없습니다.")

            cnt = 0
            for us in ulist:
                us.totalScore = 0
                us.lecDict = prob_dict.copy()
                try:
                    getUser = OIContestRK.get(user__realname=us.realname)
                    us.totalScore = getUser.total_score
                    #us.lecDict = getUser.submission_info
                    for key, value in getUser.submission_info.items():
                        sub_prob = Problem.objects.get(id=key)
                        us.lecDict[sub_prob._id] = value
                except:
                    pass

            return self.success(self.paginate_data(request, ulist, ContestSignupSerializer))
        return self.success()

class UserAdminAPI(APIView):
    @validate_serializer(ImportUserSeralizer)
    # @super_admin_required
    def post(self, request):
        """
        Import User
        """
        data = request.data["users"]

        user_list = []
        for user_data in data:
            if len(user_data) != 3 or len(user_data[0]) > 32:
                return self.error(f"Error occurred while processing data '{user_data}'")
            user_list.append(User(username=user_data[0], password=make_password(user_data[1]), email=user_data[2]))

        try:
            with transaction.atomic():
                ret = User.objects.bulk_create(user_list)
                UserProfile.objects.bulk_create([UserProfile(user=user) for user in ret])
            return self.success()
        except IntegrityError as e:
            # Extract detail from exception message
            #    duplicate key value violates unique constraint "user_username_key"
            #    DETAIL:  Key (username)=(root11) already exists.
            return self.error(str(e).split("\n")[1])

    @validate_serializer(EditUserSerializer)
    # @super_admin_required
    def put(self, request):
        """
        Edit user api
        """
        data = request.data
        try:
            user = User.objects.get(id=data["id"])
        except User.DoesNotExist:
            return self.error("User does not exist")
        if User.objects.filter(username=data["username"].lower()).exclude(id=user.id).exists():
            return self.error("Username already exists")
        if User.objects.filter(email=data["email"].lower()).exclude(id=user.id).exists():
            return self.error("Email already exists")

        pre_username = user.username
        user.username = data["username"].lower()
        user.email = data["email"].lower()
        user.admin_type = data["admin_type"]
        user.is_disabled = data["is_disabled"]
        print("datatype", data)
        if data["admin_type"] == AdminType.ADMIN:
            user.problem_permission = data["problem_permission"]
        elif data["admin_type"] == AdminType.SUPER_ADMIN:
            user.problem_permission = ProblemPermission.ALL
        else:
            user.problem_permission = ProblemPermission.NONE

        if data["password"]:
            user.set_password(data["password"])

        if data["open_api"]:
            # Avoid reset user appkey after saving changes
            if not user.open_api:
                user.open_api_appkey = rand_str()
        else:
            user.open_api_appkey = None
        user.open_api = data["open_api"]

        if data["two_factor_auth"]:
            # Avoid reset user tfa_token after saving changes
            if not user.two_factor_auth:
                user.tfa_token = rand_str()
        else:
            user.tfa_token = None

        user.two_factor_auth = data["two_factor_auth"]

        user.save()
        if pre_username != user.username:
            Submission.objects.filter(username=pre_username).update(username=user.username)

        # UserProfile.objects.filter(user=user).update(realname=data["realname"])
        User.objects.filter(id=user.id).update(realname=data["realname"])
        return self.success(UserAdminSerializer(user).data)

    # @super_admin_required
    def get(self, request):
        """
        수강과목이 있는 학생 목록을 가져오기 위한 기능
        """
        user_id = request.GET.get("id")

        lecture_id = request.GET.get("lectureid")
        contest_id = request.GET.get("contestid")
        admin_type = request.GET.get("admin_type")

        print("ADMIN :", admin_type)

        if admin_type is not None: # 프론트엔드의 Lecture.vue 파일에서 호출하는 경우
            if request.user.is_super_admin():
                print("if request.user.is_super_admin  ():")

                adminuserlist = User.objects.filter(admin_type=admin_type) | User.objects.filter(admin_type='Super Admin')

                #adminuserlist = User.objects.all()
                return self.success(self.paginate_data(request, adminuserlist, UserAdminSerializer))

        elif contest_id:
            if request.user.is_super_admin():
                try:
                    ulist = signup_class.objects.filter(contest__id=contest_id).select_related('contest').order_by(
                        "realname")  # lecture_signup_class 테이블의 모든 값, 외래키가 있는 lecture 테이블의 값을 가져온다
                    ulist = ulist.exclude(user__admin_type__in=[AdminType.ADMIN, AdminType.SUPER_ADMIN])
                except signup_class.DoesNotExist:
                    return self.error("수강중인 학생이 없습니다.")
                return self.success(self.paginate_data(request, ulist, SimpleSignupSerializer))

        if lecture_id: # 특정 수강과목을 수강중인 학생 리스트업 하는 경우
            tauser = ta_admin_class.objects.filter(user__id=request.user.id, lecture__id=lecture_id)
            if request.user.is_super_admin() or request.user.is_admin() or tauser[0].score_isallow:
                try:
                    ulist = signup_class.objects.filter(lecture=lecture_id).select_related('lecture').order_by("realname") # lecture_signup_class 테이블의 모든 값, 외래키가 있는 lecture 테이블의 값을 가져온다
                    ulist = ulist.exclude(user__admin_type__in=[AdminType.ADMIN, AdminType.SUPER_ADMIN])
                except signup_class.DoesNotExist:
                    return self.error("수강중인 학생이 없습니다.")

                #lb = LectureBuilder()
                #lb.buildLecture(ulist[0].lecture)
                #collect lecture info
                plist = Problem.objects.filter(contest__lecture=lecture_id).prefetch_related('contest')

                #test
                LectureInfo = lecDispatcher()

                cnt = 0
                for us in ulist:
                    #inlit result values
                    us.totalPractice = 0
                    us.subPractice = 0
                    us.solvePractice = 0

                    us.totalAssign = 0
                    us.subAssign = 0
                    us.solveAssign = 0

                    us.tryProblem = 0
                    us.solveProblem = 0
                    us.totalScore = 0
                    us.avgScore = 0
                    us.progress = 0
                    us.totalProblem = 0
                    us.maxScore = 0
                    us.lecDict = dict()

                    if us.user is not None and us.isallow is True:
                        #print(us.user.id,us.user.realname)
                        #print(us.score)
                        #get data from db
                        LectureInfo.fromDict(us.score)
                        us.totalPractice = LectureInfo.contAnalysis[ContestType.PRACTICE].Info.data[DataType.NUMOFCONTENTS]
                        us.subPractice = LectureInfo.contAnalysis[ContestType.PRACTICE].Info.data[DataType.NUMOFSUBCONTENTS]
                        us.solvePractice = LectureInfo.contAnalysis[ContestType.PRACTICE].Info.data[DataType.NUMOFSOLVEDCONTENTS]

                        us.totalAssign = LectureInfo.contAnalysis[ContestType.ASSIGN].Info.data[DataType.NUMOFCONTENTS]
                        us.subAssign = LectureInfo.contAnalysis[ContestType.ASSIGN].Info.data[DataType.NUMOFSUBCONTENTS]
                        us.solveAssign = LectureInfo.contAnalysis[ContestType.ASSIGN].Info.data[DataType.NUMOFSOLVEDCONTENTS]

                        us.tryProblem = LectureInfo.Info.data[DataType.NUMOFTOTALSUBPROBLEMS]
                        us.solveProblem = LectureInfo.Info.data[DataType.NUMOFTOTALSOLVEDPROBLEMS]
                        us.totalScore = LectureInfo.Info.data[DataType.SCORE]
                        us.avgScore = LectureInfo.Info.data[DataType.AVERAGE]
                        us.progress = LectureInfo.Info.data[DataType.PROGRESS]

                    us.totalProblem = LectureInfo.Info.data[DataType.NUMOFTOTALPROBLEMS]
                    us.maxScore = LectureInfo.Info.data[DataType.POINT]
                    cnt += 1

                return self.success(self.paginate_data(request, ulist, SignupSerializer))
            return self.success()

        """
        User list api / Get user by id
        """

        if user_id:
            try:
                user = User.objects.get(id=user_id)
            except User.DoesNotExist:
                return self.error("User does not exist")
            return self.success(UserAdminSerializer(user).data)

        user = User.objects.all().order_by("-create_time")

        keyword = request.GET.get("keyword", None)
        if keyword:
            user = user.filter(Q(phonenum__icontains=keyword) |
                               Q(realname__icontains=keyword) |
                               Q(username__icontains=keyword) |
                               Q(userprofile__real_name__icontains=keyword) |
                               Q(email__icontains=keyword))
        return self.success(self.paginate_data(request, user, UserAdminSerializer))

    # @super_admin_required
    def delete(self, request):
        id = request.GET.get("id")
        if id is None:
            print("Test")
        if not id:
            return self.error("Invalid Parameter, id is required")
        ids = id.split(",")
        if str(request.user.id) in ids:
            return self.error("Current user can not be deleted")
        User.objects.filter(id__in=ids).delete()
        return self.success()


class GenerateUserAPI(APIView):
    @super_admin_required
    def get(self, request):
        """
        download users excel
        """
        file_id = request.GET.get("file_id")
        if not file_id:
            return self.error("Invalid Parameter, file_id is required")
        if not re.match(r"^[a-zA-Z0-9]+$", file_id):
            return self.error("Illegal file_id")
        file_path = f"/tmp/{file_id}.xlsx"
        if not os.path.isfile(file_path):
            return self.error("File does not exist")
        with open(file_path, "rb") as f:
            raw_data = f.read()
        os.remove(file_path)
        response = HttpResponse(raw_data)
        response["Content-Disposition"] = f"attachment; filename=users.xlsx"
        response["Content-Type"] = "application/xlsx"
        return response

    @validate_serializer(GenerateUserSerializer)
    @super_admin_required
    def post(self, request):
        """
        Generate User
        """
        data = request.data
        number_max_length = max(len(str(data["number_from"])), len(str(data["number_to"])))
        if number_max_length + len(data["prefix"]) + len(data["suffix"]) > 32:
            return self.error("Username should not more than 32 characters")
        if data["number_from"] > data["number_to"]:
            return self.error("Start number must be lower than end number")

        file_id = rand_str(8)
        filename = f"/tmp/{file_id}.xlsx"
        workbook = xlsxwriter.Workbook(filename)
        worksheet = workbook.add_worksheet()
        worksheet.set_column("A:B", 20)
        worksheet.write("A1", "Username")
        worksheet.write("B1", "Password")
        i = 1

        user_list = []
        for number in range(data["number_from"], data["number_to"] + 1):
            raw_password = rand_str(data["password_length"])
            user = User(username=f"{data['prefix']}{number}{data['suffix']}", password=make_password(raw_password))
            user.raw_password = raw_password
            user_list.append(user)

        try:
            with transaction.atomic():

                ret = User.objects.bulk_create(user_list)
                UserProfile.objects.bulk_create([UserProfile(user=user) for user in ret])
                for item in user_list:
                    worksheet.write_string(i, 0, item.username)
                    worksheet.write_string(i, 1, item.raw_password)
                    i += 1
                workbook.close()
                return self.success({"file_id": file_id})
        except IntegrityError as e:
            # Extract detail from exception message
            #    duplicate key value violates unique constraint "user_username_key"
            #    DETAIL:  Key (username)=(root11) already exists.
            return self.error(str(e).split("\n")[1])
