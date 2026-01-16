"""
Comprehensive tests for JWT Authentication and RBAC.

Tests:
- User creation and authentication
- JWT token generation and validation
- Role-based access control
- Permission checking
- Audit logging
- Token expiration
- Role changes
"""

import pytest
from datetime import datetime, timedelta
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.auth.jwt_manager import (
    JWTManager,
    User,
    UserRole,
    Permission,
    ROLE_PERMISSIONS,
)


class TestUserCreation:
    """Test user creation and management."""
    
    def test_create_user(self):
        """Test creating a new user."""
        jwt_mgr = JWTManager()
        
        user = jwt_mgr.create_user(
            username="trader1",
            email="trader1@example.com",
            password="SecurePass123",
            role=UserRole.TRADER,
            full_name="John Trader",
        )
        
        assert user.username == "trader1"
        assert user.email == "trader1@example.com"
        assert user.role == UserRole.TRADER
        assert user.full_name == "John Trader"
        assert user.is_active is True
        assert user.password_hash != "SecurePass123"  # Should be hashed
    
    def test_duplicate_username_fails(self):
        """Test that duplicate usernames are rejected."""
        jwt_mgr = JWTManager()
        
        jwt_mgr.create_user("trader1", "trader1@example.com", "pass123")
        
        with pytest.raises(ValueError, match="already exists"):
            jwt_mgr.create_user("trader1", "trader2@example.com", "pass456")
    
    def test_password_is_hashed(self):
        """Test that passwords are hashed."""
        jwt_mgr = JWTManager()
        
        user = jwt_mgr.create_user("user1", "user1@example.com", "MyPassword123")
        
        # Password hash should be different from plaintext
        assert user.password_hash != "MyPassword123"
        assert len(user.password_hash) > 50  # Bcrypt hashes are long


class TestAuthentication:
    """Test user authentication."""
    
    def test_successful_authentication(self):
        """Test successful login."""
        jwt_mgr = JWTManager()
        
        jwt_mgr.create_user("trader1", "trader1@example.com", "MySecurePass")
        
        user = jwt_mgr.authenticate("trader1", "MySecurePass")
        
        assert user is not None
        assert user.username == "trader1"
        assert user.last_login is not None
    
    def test_wrong_password_fails(self):
        """Test that wrong password fails."""
        jwt_mgr = JWTManager()
        
        jwt_mgr.create_user("trader1", "trader1@example.com", "CorrectPass")
        
        user = jwt_mgr.authenticate("trader1", "WrongPass")
        
        assert user is None
    
    def test_nonexistent_user_fails(self):
        """Test that nonexistent user fails."""
        jwt_mgr = JWTManager()
        
        user = jwt_mgr.authenticate("ghost_user", "password")
        
        assert user is None
    
    def test_inactive_user_fails(self):
        """Test that inactive user cannot login."""
        jwt_mgr = JWTManager()
        
        user = jwt_mgr.create_user("trader1", "trader1@example.com", "pass123")
        user.is_active = False
        
        auth_user = jwt_mgr.authenticate("trader1", "pass123")
        
        assert auth_user is None


class TestJWTTokens:
    """Test JWT token generation and validation."""
    
    def test_create_access_token(self):
        """Test creating an access token."""
        jwt_mgr = JWTManager()
        
        user = jwt_mgr.create_user("trader1", "trader1@example.com", "pass123", role=UserRole.TRADER)
        
        token = jwt_mgr.create_access_token(user)
        
        assert token.token is not None
        assert token.token_type == "bearer"
        assert token.expires_at > datetime.utcnow()
    
    def test_verify_valid_token(self):
        """Test verifying a valid token."""
        jwt_mgr = JWTManager()
        
        user = jwt_mgr.create_user("trader1", "trader1@example.com", "pass123")
        token = jwt_mgr.create_access_token(user)
        
        payload = jwt_mgr.verify_token(token.token)
        
        assert payload is not None
        assert payload["sub"] == user.user_id
        assert payload["username"] == user.username
    
    def test_expired_token_fails(self):
        """Test that expired token is rejected."""
        jwt_mgr = JWTManager(access_token_expire_minutes=-1)  # Already expired
        
        user = jwt_mgr.create_user("trader1", "trader1@example.com", "pass123")
        token = jwt_mgr.create_access_token(user)
        
        # Token should be expired
        payload = jwt_mgr.verify_token(token.token)
        
        assert payload is None
    
    def test_get_current_user_from_token(self):
        """Test getting user from token."""
        jwt_mgr = JWTManager()
        
        created_user = jwt_mgr.create_user("trader1", "trader1@example.com", "pass123")
        token = jwt_mgr.create_access_token(created_user)
        
        retrieved_user = jwt_mgr.get_current_user(token.token)
        
        assert retrieved_user is not None
        assert retrieved_user.user_id == created_user.user_id
        assert retrieved_user.username == created_user.username
    
    def test_create_refresh_token(self):
        """Test creating a refresh token."""
        jwt_mgr = JWTManager()
        
        user = jwt_mgr.create_user("trader1", "trader1@example.com", "pass123")
        refresh_token = jwt_mgr.create_refresh_token(user)
        
        assert refresh_token is not None
        
        # Verify it's a valid token
        payload = jwt_mgr.verify_token(refresh_token)
        assert payload is not None
        assert payload["type"] == "refresh"


class TestRoleBasedAccessControl:
    """Test RBAC (Role-Based Access Control)."""
    
    def test_viewer_permissions(self):
        """Test viewer role has correct permissions."""
        jwt_mgr = JWTManager()
        
        viewer = jwt_mgr.create_user("viewer1", "viewer@example.com", "pass123", role=UserRole.VIEWER)
        
        # Should have view permissions
        assert viewer.has_permission(Permission.VIEW_DASHBOARD)
        assert viewer.has_permission(Permission.VIEW_POSITIONS)
        assert viewer.has_permission(Permission.VIEW_ORDERS)
        
        # Should NOT have modify permissions
        assert not viewer.has_permission(Permission.MODIFY_STRATEGIES)
        assert not viewer.has_permission(Permission.PLACE_ORDERS)
        assert not viewer.has_permission(Permission.EMERGENCY_HALT)
    
    def test_trader_permissions(self):
        """Test trader role has correct permissions."""
        jwt_mgr = JWTManager()
        
        trader = jwt_mgr.create_user("trader1", "trader@example.com", "pass123", role=UserRole.TRADER)
        
        # Should have view and modify permissions
        assert trader.has_permission(Permission.VIEW_DASHBOARD)
        assert trader.has_permission(Permission.MODIFY_STRATEGIES)
        assert trader.has_permission(Permission.PLACE_ORDERS)
        assert trader.has_permission(Permission.CANCEL_ORDERS)
        
        # Should NOT have admin permissions
        assert not trader.has_permission(Permission.EMERGENCY_HALT)
        assert not trader.has_permission(Permission.MANAGE_USERS)
    
    def test_admin_permissions(self):
        """Test admin role has all permissions."""
        jwt_mgr = JWTManager()
        
        admin = jwt_mgr.create_user("admin1", "admin@example.com", "pass123", role=UserRole.ADMIN)
        
        # Should have all permissions
        assert admin.has_permission(Permission.VIEW_DASHBOARD)
        assert admin.has_permission(Permission.MODIFY_STRATEGIES)
        assert admin.has_permission(Permission.EMERGENCY_HALT)
        assert admin.has_permission(Permission.MANAGE_USERS)
        assert admin.has_permission(Permission.VIEW_AUDIT_LOG)
    
    def test_require_permission_with_valid_token(self):
        """Test permission checking with valid token."""
        jwt_mgr = JWTManager()
        
        trader = jwt_mgr.create_user("trader1", "trader@example.com", "pass123", role=UserRole.TRADER)
        token = jwt_mgr.create_access_token(trader)
        
        # Trader can modify strategies
        assert jwt_mgr.require_permission(token.token, Permission.MODIFY_STRATEGIES) is True
        
        # Trader cannot trigger emergency halt
        assert jwt_mgr.require_permission(token.token, Permission.EMERGENCY_HALT) is False
    
    def test_require_permission_with_invalid_token(self):
        """Test permission checking with invalid token."""
        jwt_mgr = JWTManager()
        
        result = jwt_mgr.require_permission("invalid_token", Permission.VIEW_DASHBOARD)
        
        assert result is False


class TestAuditLogging:
    """Test audit logging functionality."""
    
    def test_audit_log_on_login(self):
        """Test that login events are logged."""
        jwt_mgr = JWTManager()
        
        jwt_mgr.create_user("trader1", "trader@example.com", "pass123")
        jwt_mgr.authenticate("trader1", "pass123")
        
        audit_log = jwt_mgr.get_audit_log()
        
        # Should have login event
        assert len(audit_log) > 0
        assert any(entry.action == "login" for entry in audit_log)
    
    def test_audit_log_on_permission_denied(self):
        """Test that permission denials are logged."""
        jwt_mgr = JWTManager()
        
        viewer = jwt_mgr.create_user("viewer1", "viewer@example.com", "pass123", role=UserRole.VIEWER)
        token = jwt_mgr.create_access_token(viewer)
        
        # Try to trigger emergency halt (should fail)
        jwt_mgr.require_permission(token.token, Permission.EMERGENCY_HALT)
        
        audit_log = jwt_mgr.get_audit_log()
        
        # Should have access_denied event
        assert any(entry.action == "access_denied" for entry in audit_log)
    
    def test_audit_log_filtering(self):
        """Test filtering audit log by user."""
        jwt_mgr = JWTManager()
        
        user1 = jwt_mgr.create_user("user1", "user1@example.com", "pass123")
        user2 = jwt_mgr.create_user("user2", "user2@example.com", "pass123")
        
        jwt_mgr.authenticate("user1", "pass123")
        jwt_mgr.authenticate("user2", "pass123")
        
        # Get audit log for user1 only
        user1_log = jwt_mgr.get_audit_log(user_id=user1.user_id)
        
        # Should only have user1's events
        assert all(entry.user_id == user1.user_id for entry in user1_log)


class TestAdminOperations:
    """Test admin-only operations."""
    
    def test_change_user_role(self):
        """Test changing user role (admin only)."""
        jwt_mgr = JWTManager()
        
        admin = jwt_mgr.create_user("admin", "admin@example.com", "pass123", role=UserRole.ADMIN)
        trader = jwt_mgr.create_user("trader1", "trader@example.com", "pass123", role=UserRole.TRADER)
        
        admin_token = jwt_mgr.create_access_token(admin)
        
        # Change trader to viewer
        success = jwt_mgr.change_user_role(admin_token.token, "trader1", UserRole.VIEWER)
        
        assert success is True
        assert trader.role == UserRole.VIEWER
    
    def test_change_role_without_admin_fails(self):
        """Test that non-admin cannot change roles."""
        jwt_mgr = JWTManager()
        
        trader = jwt_mgr.create_user("trader1", "trader@example.com", "pass123", role=UserRole.TRADER)
        trader_token = jwt_mgr.create_access_token(trader)
        
        # Try to change role (should fail)
        success = jwt_mgr.change_user_role(trader_token.token, "trader1", UserRole.ADMIN)
        
        assert success is False
    
    def test_deactivate_user(self):
        """Test deactivating a user."""
        jwt_mgr = JWTManager()
        
        admin = jwt_mgr.create_user("admin", "admin@example.com", "pass123", role=UserRole.ADMIN)
        trader = jwt_mgr.create_user("trader1", "trader@example.com", "pass123", role=UserRole.TRADER)
        
        admin_token = jwt_mgr.create_access_token(admin)
        
        # Deactivate trader
        success = jwt_mgr.deactivate_user(admin_token.token, "trader1")
        
        assert success is True
        assert trader.is_active is False


class TestTokenRevocation:
    """Test token revocation (logout)."""
    
    def test_revoke_token(self):
        """Test revoking a token."""
        jwt_mgr = JWTManager()
        
        user = jwt_mgr.create_user("trader1", "trader@example.com", "pass123")
        token = jwt_mgr.create_access_token(user)
        
        # Token should be in active sessions
        assert token.token in jwt_mgr.active_sessions
        
        # Revoke it
        jwt_mgr.revoke_token(token.token)
        
        # Should no longer be in active sessions
        assert token.token not in jwt_mgr.active_sessions


class TestEdgeCases:
    """Test edge cases and security."""
    
    def test_empty_password(self):
        """Test creating user with empty password."""
        jwt_mgr = JWTManager()
        
        user = jwt_mgr.create_user("user1", "user1@example.com", "")
        
        # Should still hash empty password
        assert user.password_hash != ""
    
    def test_permission_enum_coverage(self):
        """Test that all roles have defined permissions."""
        # Ensure all roles have permissions defined
        for role in UserRole:
            assert role in ROLE_PERMISSIONS
            assert len(ROLE_PERMISSIONS[role]) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
