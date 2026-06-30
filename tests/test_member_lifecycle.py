"""Member lifecycle (§8.3 follow-up): self-leave + admin role-change, audited.

Both are view-layer, audited via dotted emit(), with authz + safety guards
(least-privilege role change, same-community IDOR, last-admin protection).
"""

import pytest
from django.test import Client
from django.urls import reverse

from apps.audit.models import AuditLog
from apps.communities.models import Member
from tests.factories import CommunityFactory, MemberFactory


@pytest.fixture
def login():
    def _l(user):
        c = Client()
        c.force_login(user)
        return c

    return _l


def rows(action):
    return AuditLog.objects.filter(action=action)


@pytest.mark.django_db
class TestMemberLeave:
    def test_member_can_leave_soft_and_audited(self, login):
        comm = CommunityFactory()
        MemberFactory(community=comm, role="admin")  # another admin remains
        leaver = MemberFactory(community=comm, role="member")
        resp = login(leaver.user).post(reverse("community-leave", kwargs={"slug": comm.slug}))
        assert resp.status_code in (200, 302)
        leaver.refresh_from_db()
        assert leaver.is_active is False  # soft leave (archive, not delete)
        assert Member.objects.filter(pk=leaver.pk).exists()  # row preserved
        ml = rows("member.left").filter(resource_id=leaver.id)
        assert ml.count() == 1 and ml.get().user_id == leaver.user_id

    def test_last_admin_cannot_leave(self, login):
        comm = CommunityFactory()
        only_admin = MemberFactory(community=comm, role="admin")
        resp = login(only_admin.user).post(reverse("community-leave", kwargs={"slug": comm.slug}))
        assert resp.status_code in (200, 302)
        only_admin.refresh_from_db()
        assert only_admin.is_active is True  # blocked — would orphan the community
        assert rows("member.left").count() == 0


@pytest.mark.django_db
class TestRoleChange:
    def _post(self, login, comm, actor, target, role):
        return login(actor.user).post(
            reverse("community-settings", kwargs={"slug": comm.slug}),
            {"action": "change_role", "member_id": str(target.id), "role": role},
        )

    def test_admin_changes_role_audited(self, login):
        comm = CommunityFactory()
        admin = MemberFactory(community=comm, role="admin")
        target = MemberFactory(community=comm, role="member")
        resp = self._post(login, comm, admin, target, "coordinator")
        assert resp.status_code in (200, 302)
        target.refresh_from_db()
        assert target.role == "coordinator"
        rc = rows("member.role_changed").filter(resource_id=target.id)
        assert rc.count() == 1
        assert (rc.get().details or {}).get("from") == "member"
        assert (rc.get().details or {}).get("to") == "coordinator"
        assert rc.get().user_id == admin.user_id

    def test_coordinator_cannot_change_role(self, login):
        comm = CommunityFactory()
        MemberFactory(community=comm, role="admin")
        coord = MemberFactory(community=comm, role="coordinator")  # can reach settings, not change roles
        target = MemberFactory(community=comm, role="member")
        self._post(login, comm, coord, target, "admin")
        target.refresh_from_db()
        assert target.role == "member"  # least-privilege: coordinators can't change roles
        assert rows("member.role_changed").count() == 0

    def test_cross_community_idor_blocked(self, login):
        comm = CommunityFactory()
        other = CommunityFactory()
        admin = MemberFactory(community=comm, role="admin")
        victim = MemberFactory(community=other, role="member")  # different community
        self._post(login, comm, admin, victim, "admin")
        victim.refresh_from_db()
        assert victim.role == "member"  # untouched
        assert rows("member.role_changed").count() == 0

    def test_cannot_demote_last_admin(self, login):
        comm = CommunityFactory()
        only_admin = MemberFactory(community=comm, role="admin")
        self._post(login, comm, only_admin, only_admin, "member")
        only_admin.refresh_from_db()
        assert only_admin.role == "admin"  # blocked — community must keep an admin
        assert rows("member.role_changed").count() == 0
