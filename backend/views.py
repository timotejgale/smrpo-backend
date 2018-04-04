from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404
from rest_framework.parsers import JSONParser
from backend.models import User, Role, AllowedRole, DeveloperGroup, DeveloperGroupMembership, GroupRole, Project
from backend.serializers import UserSerializer, DeveloperGroupSerializer, AllowedRoleSerializer, RoleSerializer, DeveloperGroupMembershipSerializer, ProjectSerializer
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework import generics
from rest_framework import views
from rest_framework import permissions

from rest_framework_swagger.renderers import OpenAPIRenderer, SwaggerUIRenderer
from rest_framework.decorators import api_view, renderer_classes
from rest_framework import response, schemas
from . import urls

import uuid

# TODO: remove session auth, remove auth for swagger
@api_view()
@renderer_classes([SwaggerUIRenderer, OpenAPIRenderer])
def schema_view(request):
    """
    Schema for swagger
    """
    generator = schemas.SchemaGenerator(title='API Docs', patterns=urls.urlpatterns, url='/')
    return response.Response(generator.get_schema())

class InvalidateToken(views.APIView):
    """
    Use this endpoint to log out all sessions for a given user (jwt).

    Basically invalidate all issued jwt tokens. Not really needed but hey, it's there and it works.
    """
    permission_classes = [permissions.IsAuthenticated]
    def post(self, request, *args, **kwargs):
        user = request.user
        user.jwt_secret = uuid.uuid4()
        user.save()
        return Response(status=status.HTTP_204_NO_CONTENT)

class SingleUser(views.APIView):
    """
    Retrieve all information (or most of it) about a single user. Search by email.
    """

    def get(self, request, **kwargs):
        roles = Role.objects.all()
        allowed_roles = AllowedRole.objects.all()
        #user = User.objects.all().filter(email=kwargs["email"]).values_list('email', 'name', 'id')
        user = get_object_or_404(User, email=kwargs["email"])

        roles_list = []
        allowed_roles_query = allowed_roles.filter(user_id=user.id)
        for query in allowed_roles_query:
            roles_query = roles.filter(id=query.role_id.id)
            roles_list.append(roles_query[0].title)
        user_allowed_roles = UserSerializer(user).data
        user_allowed_roles["roles"] = roles_list
        for key in ["password", "last_login", "first_name", "last_name", "is_staff",
                        "date_joined", "jwt_secret", "groups", "user_permissions", "username"]:
            del user_allowed_roles[key]

        return Response(user_allowed_roles, status=status.HTTP_202_ACCEPTED)


class UserList(generics.ListCreateAPIView):
    """
    List all users, or create a new one.
    """

    queryset = User.objects.all()
    serializer_class = UserSerializer

    def get(self, request, **kwargs):
        roles = Role.objects.all()
        allowed_roles = AllowedRole.objects.all()
        users = User.objects.all().filter(is_superuser=False).order_by("surname")

        user_roles = []
        for user in users:
            roles_list = []
            allowed_roles_query = allowed_roles.filter(user_id=user.id)
            for query in allowed_roles_query:
                roles_query = roles.filter(id=query.role_id.id)
                roles_list.append(roles_query[0].title)
            user_allowed_roles = UserSerializer(user).data
            user_allowed_roles["roles"] = roles_list
            user_roles.append(user_allowed_roles)

        return Response(user_roles, status=status.HTTP_202_ACCEPTED)

    def post(self, request, **kwargs):
        data = JSONParser().parse(request)
        print(data)
        serializer = UserSerializer(data=data)

        success_status=False

        if serializer.is_valid():
            success_status=True
            serializer.save()
        else:
            pass

        if "roles" in data:
            user_id = serializer.data["id"]
            for role_id in data["roles"]:
                user = User.objects.get(pk=user_id)
                role = Role.objects.get(pk=role_id)
                AllowedRole.objects.create(user_id=user, role_id=role)

        if success_status:
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        return JsonResponse(serializer.errors, status=status.HTTP_406_NOT_ACCEPTABLE)


class UserUpdate(generics.UpdateAPIView):
    """
    Update user.
    """

    queryset = User.objects.all()
    serializer_class = UserSerializer

    def put(self, request, *args, **kwargs):
        try:
            user = User.objects.get(pk=kwargs["pk"])
        except User.DoesNotExist:
            return HttpResponse(status=404)

        data = JSONParser().parse(request)

        # Set to existing hash if password is null.
        if data["password"] is None:
            data["password"] = getattr(user, "password")

        serializer = UserSerializer(user, data=data)

        success_status=False

        if serializer.is_valid():
            success_status=True
            serializer.save()
        else:
            print(serializer.errors)

        if "roles" in data:
            user_id = serializer.data["id"]
            allowed_roles = AllowedRole.objects.filter(user_id=user_id)
            for role in data["roles"]:
                if role not in list(allowed_roles.values_list('role_id', flat=True)):
                    user = User.objects.get(pk=user_id)
                    roles = Role.objects.get(pk=role)
                    AllowedRole.objects.create(user_id=user, role_id=roles)
            for i in allowed_roles:
                if i.role_id.id not in data["roles"]:
                    i.delete()

        if success_status:
            return JsonResponse(serializer.data, status=status.HTTP_200_OK)

        return JsonResponse(serializer.errors, status=status.HTTP_406_NOT_ACCEPTABLE)


def get_user_group_roles(dev_group_memb_id):
    """
    Get all user roles on DeveloperGroup
    """

    roles = Role.objects.all()
    group_roles = GroupRole.objects.all()

    roles_list = []
    group_roles_query = group_roles.filter(developer_group_membership_id=dev_group_memb_id)
    for query in group_roles_query:
        roles_query = roles.filter(id=query.role_id.id)
        roles_list.append(roles_query[0].id)

    return roles_list


class DeveloperGroupList(generics.ListCreateAPIView):
    """
    List all groups.
    """

    queryset = DeveloperGroup.objects.all()
    serializer_class = DeveloperGroupSerializer

    def get(self, request, **kwargs):
        groups = DeveloperGroup.objects.all()
        group_memberships = DeveloperGroupMembership.objects.all()
        users = User.objects.all()

        group_roles = []
        for group in groups:
            allowed_roles_query = group_memberships.filter(
                developer_group_id=group.id)
            group_data = DeveloperGroupSerializer(group).data
            user_roles_dict = []
            for z in allowed_roles_query:
                user_roles = get_user_group_roles(z.id)
                user_details = users.filter(id=z.user_id.id)[0]
                user_data = UserSerializer(user_details).data
                user_data["allowed_group_roles"] = user_roles
                user_data["group_active"] = z.active
                user_roles_dict.append(user_data)
            group_data["users"] = user_roles_dict
            group_roles.append(group_data)

        return Response(group_roles, status=status.HTTP_202_ACCEPTED)

    def post(self, request, **kwargs):
        data = JSONParser().parse(request)
        developer_group_title=data["title"]
        developer_group = DeveloperGroup(title=developer_group_title)
        developer_group.save()

        for user_data in data["users"]:
            user = User.objects.get(pk=user_data["id"])
            developer_group = DeveloperGroup.objects.get(pk=developer_group.id)
            developer_group_membership = DeveloperGroupMembership(user_id=user, developer_group_id=developer_group, active=user_data["group_active"])
            developer_group_membership.save()

            for group_role in user_data["allowed_group_roles"]:
                role = Role.objects.get(pk=group_role)
                GroupRole.objects.create(developer_group_membership_id=developer_group_membership, role_id=role)

        return Response(data=None, status=status.HTTP_200_OK)

from datetime import datetime
class DeveloperGroupDetail(generics.RetrieveUpdateDestroyAPIView):
    """
    Retrieve, update or delete a developer group.
    """

    queryset = DeveloperGroup.objects.all()
    serializer_class = DeveloperGroupSerializer

    def get(self, request, **kwargs):
        group = DeveloperGroup.objects.get(pk=kwargs["pk"])
        group_memberships = DeveloperGroupMembership.objects.all()
        users = User.objects.all()

        group_roles = []
        allowed_roles_query = group_memberships.filter(
            developer_group_id=group.id)
        group_data = DeveloperGroupSerializer(group).data
        user_roles_dict = []
        for z in allowed_roles_query:
            user_roles = get_user_group_roles(z.id)
            user_details = users.filter(id=z.user_id.id)[0]
            user_data = UserSerializer(user_details).data
            user_data["allowed_group_roles"] = user_roles
            user_data["group_active"] = z.active
            user_roles_dict.append(user_data)
        group_data["users"] = user_roles_dict
        group_roles.append(group_data)

        return Response(group_roles, status=status.HTTP_202_ACCEPTED)

    def put(self, request, *args, **kwargs):
        data = JSONParser().parse(request)
        group = DeveloperGroup.objects.get(pk=kwargs["pk"])
        group.title = data["title"]
        group.save()

        developer_group_membership_list = list(
            DeveloperGroupMembership.objects.filter(
                developer_group_id=kwargs["pk"]).values_list('user_id',
                                                             flat=True))

        developer_group_membership = DeveloperGroupMembership.objects.filter(
            developer_group_id=kwargs["pk"])

        for user_data in data["users"]:
            user_id = user_data["id"]

            if user_id not in developer_group_membership_list:
                user = User.objects.get(pk=user_id)
                developer_group = DeveloperGroup.objects.get(
                    pk=kwargs["pk"])
                developer_group_membership = DeveloperGroupMembership(
                    user_id=user, developer_group_id=developer_group,
                    active=user_data["group_active"])
                developer_group_membership.save()

                for group_role in user_data["allowed_group_roles"]:
                    role = Role.objects.get(pk=group_role)
                    GroupRole.objects.create(
                        developer_group_membership_id=developer_group_membership,
                        role_id=role)
            else:
                developer_group_membership_user = developer_group_membership.get(user_id=user_id)
                if developer_group_membership_user.active == False and user_data["group_active"] == True:
                    developer_group_membership_user.deleted_at = None
                else:
                    developer_group_membership_user.deleted_at = datetime.now()
                developer_group_membership_user.active = user_data["group_active"]
                developer_group_membership_user.save()

                allowed_roles = GroupRole.objects.filter(developer_group_membership_id=developer_group_membership_user.id)

                for role in user_data["allowed_group_roles"]:
                    if role not in list(
                            allowed_roles.values_list('role_id', flat=True)):
                        roles = Role.objects.get(pk=role)
                        GroupRole.objects.create(developer_group_membership_id=developer_group_membership_user, role_id=roles)
                for i in allowed_roles:
                    if i.role_id.id not in user_data["allowed_group_roles"]:
                        i.delete()

        return Response(data=None, status=status.HTTP_200_OK)


class RoleList(generics.ListAPIView):
    """
    List all roles, or create a new one.
    """

    def get(self, request, *args, **kwargs):
        roles = Role.objects.all()

        all_roles = []
        for i in roles:
            all_roles.append(i.title)

        return JsonResponse(all_roles, safe=False, status=status.HTTP_202_ACCEPTED)


class ProjectList(generics.ListCreateAPIView):
    """
    List all groups.
    """

    queryset = Project.objects.all()
    serializer_class = ProjectSerializer


    def get(self, request, **kwargs):
        projects = Project.objects.all()
        group_memberships = DeveloperGroupMembership.objects.all()
        users = User.objects.all()

        projects_data = []
        for project in projects:
            allowed_roles_query = group_memberships.filter(
                developer_group_id=project.developer_group_id.id)
            group_data = DeveloperGroupSerializer(
                project.developer_group_id).data
            project_data = ProjectSerializer(project).data
            project_data["group_data"] = group_data

            user_roles_dict = []
            for z in allowed_roles_query:
                user_roles = get_user_group_roles(z.id)
                user_details = users.filter(id=z.user_id.id)[0]
                user_data = UserSerializer(user_details).data
                user_data["allowed_group_roles"] = user_roles
                user_data["group_active"] = z.active
                user_roles_dict.append(user_data)
            group_data["users"] = user_roles_dict
            projects_data.append(project_data)

        return Response(projects_data, status=status.HTTP_202_ACCEPTED)
