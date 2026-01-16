"""
JWT-based Authentication System with Role-Based Access Control (RBAC).

Provides institutional-grade authentication:
- JWT token generation and validation
- Role-based access control (Trader, Viewer, Admin)
- Token refresh mechanism
- Audit logging of all access
- Multi-user session management

Critical for team/institutional deployments.
"""

import os
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Set
from dataclasses import dataclass, field
from enum import Enum
import jwt
from passlib.context import CryptContext
import structlog

logger = structlog.get_logger(__name__)

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class UserRole(str, Enum):
    """User roles with hierarchical permissions."""
    VIEWER = "viewer"       # Read-only access (view dashboard)
    TRADER = "trader"       # Can modify strategies, but not halt
    ADMIN = "admin"         # Full control including emergency halt


class Permission(str, Enum):
    """Granular permissions."""
    VIEW_DASHBOARD = "view:dashboard"
    VIEW_POSITIONS = "view:positions"
    VIEW_ORDERS = "view:orders"
    VIEW_METRICS = "view:metrics"
    VIEW_LOGS = "view:logs"
    
    MODIFY_STRATEGIES = "modify:strategies"
    PLACE_ORDERS = "place:orders"
    CANCEL_ORDERS = "cancel:orders"
    
    EMERGENCY_HALT = "admin:emergency_halt"
    MANAGE_USERS = "admin:manage_users"
    VIEW_AUDIT_LOG = "admin:audit_log"


# Role -> Permissions mapping
ROLE_PERMISSIONS: Dict[UserRole, Set[Permission]] = {
    UserRole.VIEWER: {
        Permission.VIEW_DASHBOARD,
        Permission.VIEW_POSITIONS,
        Permission.VIEW_ORDERS,
        Permission.VIEW_METRICS,
    },
    UserRole.TRADER: {
        # Has all viewer permissions plus:
        Permission.VIEW_DASHBOARD,
        Permission.VIEW_POSITIONS,
        Permission.VIEW_ORDERS,
        Permission.VIEW_METRICS,
        Permission.VIEW_LOGS,
        Permission.MODIFY_STRATEGIES,
        Permission.PLACE_ORDERS,
        Permission.CANCEL_ORDERS,
    },
    UserRole.ADMIN: {
        # Has all permissions
        Permission.VIEW_DASHBOARD,
        Permission.VIEW_POSITIONS,
        Permission.VIEW_ORDERS,
        Permission.VIEW_METRICS,
        Permission.VIEW_LOGS,
        Permission.MODIFY_STRATEGIES,
        Permission.PLACE_ORDERS,
        Permission.CANCEL_ORDERS,
        Permission.EMERGENCY_HALT,
        Permission.MANAGE_USERS,
        Permission.VIEW_AUDIT_LOG,
    },
}


@dataclass
class User:
    """User account."""
    user_id: str
    username: str
    email: str
    password_hash: str
    role: UserRole
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_login: Optional[datetime] = None
    is_active: bool = True
    full_name: Optional[str] = None
    
    def has_permission(self, permission: Permission) -> bool:
        """Check if user has a specific permission."""
        return permission in ROLE_PERMISSIONS.get(self.role, set())
    
    def can(self, permission: Permission) -> bool:
        """Alias for has_permission."""
        return self.has_permission(permission)


@dataclass
class AccessToken:
    """JWT access token."""
    token: str
    token_type: str = "bearer"
    expires_at: datetime = field(default_factory=lambda: datetime.utcnow() + timedelta(hours=1))
    
    @property
    def is_expired(self) -> bool:
        """Check if token is expired."""
        return datetime.utcnow() >= self.expires_at


@dataclass
class AuditLogEntry:
    """Audit log entry for compliance."""
    timestamp: datetime
    user_id: str
    username: str
    action: str
    resource: str
    ip_address: Optional[str]
    success: bool
    details: Optional[Dict] = None


class JWTManager:
    """
    Manages JWT authentication and RBAC.
    
    Features:
    - Secure JWT token generation
    - Token validation and refresh
    - Password hashing with bcrypt
    - Role-based access control
    - Audit logging
    - Session management
    """
    
    def __init__(
        self,
        secret_key: Optional[str] = None,
        algorithm: str = "HS256",
        access_token_expire_minutes: int = 60,
        refresh_token_expire_days: int = 7,
    ):
        self.secret_key = secret_key or os.environ.get("JWT_SECRET_KEY") or secrets.token_urlsafe(32)
        self.algorithm = algorithm
        self.access_token_expire = timedelta(minutes=access_token_expire_minutes)
        self.refresh_token_expire = timedelta(days=refresh_token_expire_days)
        
        # In-memory user store (in production, use database)
        self.users: Dict[str, User] = {}
        
        # In-memory audit log (in production, use persistent storage)
        self.audit_log: List[AuditLogEntry] = []
        
        # Active sessions
        self.active_sessions: Dict[str, str] = {}  # token -> user_id
        
        logger.info("jwt_manager_initialized")
    
    def create_user(
        self,
        username: str,
        email: str,
        password: str,
        role: UserRole = UserRole.VIEWER,
        full_name: Optional[str] = None,
    ) -> User:
        """
        Create a new user.
        
        Args:
            username: Unique username
            email: User email
            password: Plain text password (will be hashed)
            role: User role
            full_name: Optional full name
        
        Returns:
            Created User object
        
        Raises:
            ValueError: If username already exists
        """
        if username in self.users:
            raise ValueError(f"Username '{username}' already exists")
        
        user_id = secrets.token_urlsafe(16)
        
        # Bcrypt has a 72-byte limit, truncate if necessary
        password_bytes = password.encode('utf-8')[:72]
        password_hash = pwd_context.hash(password_bytes.decode('utf-8'))
        
        user = User(
            user_id=user_id,
            username=username,
            email=email,
            password_hash=password_hash,
            role=role,
            full_name=full_name,
        )
        
        self.users[username] = user
        
        logger.info(
            "user_created",
            username=username,
            role=role.value,
            user_id=user_id,
        )
        
        return user
    
    def authenticate(self, username: str, password: str) -> Optional[User]:
        """
        Authenticate user with username and password.
        
        Args:
            username: Username
            password: Plain text password
        
        Returns:
            User object if authentication successful, None otherwise
        """
        user = self.users.get(username)
        
        if not user:
            logger.warning("auth_failed_user_not_found", username=username)
            return None
        
        if not user.is_active:
            logger.warning("auth_failed_user_inactive", username=username)
            return None
        
        if not pwd_context.verify(password, user.password_hash):
            logger.warning("auth_failed_invalid_password", username=username)
            self._log_audit(
                user_id="unknown",
                username=username,
                action="login",
                resource="auth",
                success=False,
            )
            return None
        
        # Update last login
        user.last_login = datetime.utcnow()
        
        logger.info("auth_success", username=username, user_id=user.user_id)
        
        self._log_audit(
            user_id=user.user_id,
            username=username,
            action="login",
            resource="auth",
            success=True,
        )
        
        return user
    
    def create_access_token(
        self,
        user: User,
        expires_delta: Optional[timedelta] = None,
    ) -> AccessToken:
        """
        Create a JWT access token.
        
        Args:
            user: User object
            expires_delta: Optional custom expiration time
        
        Returns:
            AccessToken object
        """
        expires = datetime.utcnow() + (expires_delta or self.access_token_expire)
        
        to_encode = {
            "sub": user.user_id,
            "username": user.username,
            "role": user.role.value,
            "exp": expires,
            "iat": datetime.utcnow(),
            "type": "access",
        }
        
        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
        
        # Track active session
        self.active_sessions[encoded_jwt] = user.user_id
        
        logger.debug(
            "access_token_created",
            username=user.username,
            expires=expires.isoformat(),
        )
        
        return AccessToken(token=encoded_jwt, expires_at=expires)
    
    def create_refresh_token(self, user: User) -> str:
        """
        Create a JWT refresh token.
        
        Args:
            user: User object
        
        Returns:
            Refresh token string
        """
        expires = datetime.utcnow() + self.refresh_token_expire
        
        to_encode = {
            "sub": user.user_id,
            "exp": expires,
            "iat": datetime.utcnow(),
            "type": "refresh",
        }
        
        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
        
        logger.debug(
            "refresh_token_created",
            username=user.username,
            expires=expires.isoformat(),
        )
        
        return encoded_jwt
    
    def verify_token(self, token: str) -> Optional[Dict]:
        """
        Verify and decode a JWT token.
        
        Args:
            token: JWT token string
        
        Returns:
            Decoded payload if valid, None otherwise
        """
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            return payload
        except jwt.ExpiredSignatureError:
            logger.warning("token_expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning("token_invalid", error=str(e))
            return None
    
    def get_current_user(self, token: str) -> Optional[User]:
        """
        Get user from token.
        
        Args:
            token: JWT token string
        
        Returns:
            User object if token is valid, None otherwise
        """
        payload = self.verify_token(token)
        
        if not payload:
            return None
        
        user_id = payload.get("sub")
        username = payload.get("username")
        
        # Find user by username
        user = self.users.get(username)
        
        if not user or user.user_id != user_id:
            logger.warning("user_not_found_from_token", user_id=user_id)
            return None
        
        if not user.is_active:
            logger.warning("inactive_user_attempted_access", username=username)
            return None
        
        return user
    
    def require_permission(self, token: str, permission: Permission) -> bool:
        """
        Check if token has required permission.
        
        Args:
            token: JWT token
            permission: Required permission
        
        Returns:
            True if authorized, False otherwise
        """
        user = self.get_current_user(token)
        
        if not user:
            return False
        
        has_perm = user.has_permission(permission)
        
        if not has_perm:
            logger.warning(
                "permission_denied",
                username=user.username,
                permission=permission.value,
                role=user.role.value,
            )
            
            self._log_audit(
                user_id=user.user_id,
                username=user.username,
                action="access_denied",
                resource=permission.value,
                success=False,
            )
        
        return has_perm
    
    def revoke_token(self, token: str):
        """
        Revoke a token (logout).
        
        Args:
            token: JWT token to revoke
        """
        if token in self.active_sessions:
            user_id = self.active_sessions[token]
            del self.active_sessions[token]
            logger.info("token_revoked", user_id=user_id)
    
    def _log_audit(
        self,
        user_id: str,
        username: str,
        action: str,
        resource: str,
        success: bool,
        ip_address: Optional[str] = None,
        details: Optional[Dict] = None,
    ):
        """Log audit event."""
        entry = AuditLogEntry(
            timestamp=datetime.utcnow(),
            user_id=user_id,
            username=username,
            action=action,
            resource=resource,
            ip_address=ip_address,
            success=success,
            details=details,
        )
        
        self.audit_log.append(entry)
        
        logger.info(
            "audit_log",
            user_id=user_id,
            username=username,
            action=action,
            resource=resource,
            success=success,
        )
    
    def get_audit_log(
        self,
        user_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[AuditLogEntry]:
        """
        Get audit log entries.
        
        Args:
            user_id: Optional user ID filter
            start_time: Optional start time
            end_time: Optional end time
            limit: Maximum number of entries
        
        Returns:
            List of audit log entries
        """
        entries = self.audit_log
        
        if user_id:
            entries = [e for e in entries if e.user_id == user_id]
        
        if start_time:
            entries = [e for e in entries if e.timestamp >= start_time]
        
        if end_time:
            entries = [e for e in entries if e.timestamp <= end_time]
        
        # Sort by timestamp (newest first)
        entries.sort(key=lambda x: x.timestamp, reverse=True)
        
        return entries[:limit]
    
    def change_user_role(self, admin_token: str, username: str, new_role: UserRole) -> bool:
        """
        Change user role (admin only).
        
        Args:
            admin_token: Admin JWT token
            username: Username to modify
            new_role: New role
        
        Returns:
            True if successful, False otherwise
        """
        # Verify admin permission
        if not self.require_permission(admin_token, Permission.MANAGE_USERS):
            return False
        
        admin_user = self.get_current_user(admin_token)
        
        if username not in self.users:
            logger.warning("change_role_failed_user_not_found", username=username)
            return False
        
        user = self.users[username]
        old_role = user.role
        user.role = new_role
        
        logger.info(
            "user_role_changed",
            username=username,
            old_role=old_role.value,
            new_role=new_role.value,
            admin=admin_user.username,
        )
        
        self._log_audit(
            user_id=admin_user.user_id,
            username=admin_user.username,
            action="change_role",
            resource=f"user:{username}",
            success=True,
            details={"old_role": old_role.value, "new_role": new_role.value},
        )
        
        return True
    
    def deactivate_user(self, admin_token: str, username: str) -> bool:
        """
        Deactivate a user (admin only).
        
        Args:
            admin_token: Admin JWT token
            username: Username to deactivate
        
        Returns:
            True if successful, False otherwise
        """
        if not self.require_permission(admin_token, Permission.MANAGE_USERS):
            return False
        
        admin_user = self.get_current_user(admin_token)
        
        if username not in self.users:
            return False
        
        user = self.users[username]
        user.is_active = False
        
        logger.info(
            "user_deactivated",
            username=username,
            admin=admin_user.username,
        )
        
        self._log_audit(
            user_id=admin_user.user_id,
            username=admin_user.username,
            action="deactivate_user",
            resource=f"user:{username}",
            success=True,
        )
        
        return True
