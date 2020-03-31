import os
import re
import xlsxwriter

from django.db import transaction, IntegrityError
from django.db.models import Q
from django.http import HttpResponse
from django.contrib.auth.hashers import make_password

from submission.models import Submission
from utils.api import APIView, validate_serializer
from utils.shortcuts import rand_str
from lecture.models import signup_class
from problem.models import Problem

from ..decorators import super_admin_required
from ..models import AdminType, ProblemPermission, User, UserProfile
from ..serializers import EditUserSerializer, UserAdminSerializer, GenerateUserSerializer
from ..serializers import ImportUserSeralizer, SignupSerializer
from django.db.models import Max
from lecture.views.stdResult import RefLecture, SubmitLecture


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

        UserProfile.objects.filter(user=user).update(real_name=data["real_name"])
        return self.success(UserAdminSerializer(user).data)

    # @super_admin_required
    def get(self, request):
        """
        수강과목이 있는 학생 목록을 가져오기 위한 기능
        """

        user_id = request.GET.get("id")

        lecture_id = request.GET.get("lectureid")

        if lecture_id: # 특정 수강과목을 수강중인 학생 리스트업 하는 경우
            try:
                ulist = signup_class.objects.filter(lecture=lecture_id).select_related('lecture').order_by("realname") # lecture_signup_class 테이블의 모든 값, 외래키가 있는 lecture 테이블의 값을 가져온다
                ulist = ulist.exclude(user__admin_type__in=[AdminType.ADMIN, AdminType.SUPER_ADMIN])
            except signup_class.DoesNotExist:
                return self.error("수강중인 학생이 없습니다.")


            #collect lecture info
            plist = Problem.objects.filter(contest__lecture=lecture_id).prefetch_related('contest')

            #input Problem Structure in Lecture
            LectureInfo = RefLecture()
            #print("Problem List")
            for p in plist:
                # print(p.id,p.title,p.visible)
                LectureInfo.addProblem(p)
                #print(p,p.title,p.contest)

            #get Submission
            sublist = Submission.objects.filter(lecture=lecture_id)

            for us in ulist:

                #inlit result values
                us.tryProblem = 0
                us.solveProblem = 0
                us.totalScore = 0
                us.avgScore = 0
                us.progress = 0
                us.totalProblem = 0
                us.maxScore = 0

                if us.user is not None:
                    #print(us.user.id,us.user.realname)
                    #get data from db
                    ldates = sublist.filter(user=us.user).values('contest','problem').annotate(latest_created_at=Max('create_time'))
                    sdata = sublist.filter(create_time__in=ldates.values('latest_created_at')).order_by('-create_time')

                    student = SubmitLecture(us, LectureInfo)

                    for submit in sdata:
                        # if us.user.username == 'djg05105':
                        #     print(submit.id, submit.problem_id, submit.problem.title, submit.result)
                        student.addSubmission(submit)

                    us.tryProblem = student.submittedProblems
                    us.solveProblem = student.passedProblems
                    us.totalScore = student.totalscore
                    us.avgScore = student.problemAverage
                    us.progress = round(student.progress)

                us.totalProblem = LectureInfo.numofProblems
                us.maxScore = LectureInfo.totalscore

            return self.success(self.paginate_data(request, ulist, SignupSerializer))

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
            user = user.filter(Q(username__icontains=keyword) |
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
