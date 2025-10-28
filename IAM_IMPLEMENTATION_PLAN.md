# LEMMA IAM - COMPLETE IMPLEMENTATION PLAN
**Goal:** Build IAM platform on top of existing verification engine  
**Timeline:** 4 weeks (2 sprints × 2 weeks) - Foundation already built!  
**Status:** Sprint 1 Week 1 PARTIALLY COMPLETE → Building missing pieces

## ✅ **ALREADY BUILT (Found in codebase):**
- ✅ Database schema with sites, permissions, user_permissions tables
- ✅ Permission Management API (create, grant, revoke permissions)
- ✅ Site registration with unique crypto keys
- ✅ Access verification with Rust crypto engine
- ✅ Database models for testing
- ✅ OAuth endpoints (basic)

## ❌ **STILL NEEDED:**
- ❌ Permission Types system (structured types)
- ❌ Permission Policies engine (complex rules)
- ❌ Bulk operations (CSV upload)
- ❌ Admin Dashboard UI
- ❌ Analytics endpoints
- ❌ Audit Log API
- ❌ Developer SDKs

---

## 🎯 SPRINT 1: PERMISSION FOUNDATION (Weeks 1-2)
**Goal:** Ship basic permission management that customers can use

### Week 1: Database Schema + Core APIs

#### Day 1-2: Database Schema
```sql
-- migrations/003_iam_permission_system.sql

-- Permission Types (templates developers create)
CREATE TABLE permission_types (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) UNIQUE NOT NULL,  -- 'admin', 'premium_tier_1'
    type VARCHAR(50) NOT NULL,           -- 'role', 'scope', 'time-bound', 'attribute'
    description TEXT,
    config JSONB DEFAULT '{}',           -- Type-specific config
    created_at TIMESTAMP DEFAULT NOW(),
    created_by VARCHAR(255),             -- Who created this type
    site_id INTEGER REFERENCES sites(id),
    active BOOLEAN DEFAULT true
);

-- Permission Instances (actual issued permissions)
CREATE TABLE permission_instances (
    id SERIAL PRIMARY KEY,
    permission_type_id INTEGER REFERENCES permission_types(id),
    credential_did VARCHAR(255) NOT NULL,  -- Link to credential
    email VARCHAR(255) NOT NULL,
    granted_at TIMESTAMP DEFAULT NOW(),
    granted_by VARCHAR(255),
    expires_at TIMESTAMP,                  -- NULL = never expires
    revoked_at TIMESTAMP,
    revoked_by VARCHAR(255),
    revocation_reason TEXT,
    metadata JSONB DEFAULT '{}'            -- Custom attributes
);

-- Permission Policies (complex permission rules)
CREATE TABLE permission_policies (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) UNIQUE NOT NULL,
    description TEXT,
    rules JSONB NOT NULL,                  -- Policy definition
    site_id INTEGER REFERENCES sites(id),
    created_at TIMESTAMP DEFAULT NOW(),
    active BOOLEAN DEFAULT true
);

-- User Profiles (for IAM)
CREATE TABLE iam_user_profiles (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    display_name VARCHAR(255),
    avatar_url TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    last_login TIMESTAMP,
    metadata JSONB DEFAULT '{}'
);

-- Audit Log
CREATE TABLE iam_audit_log (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT NOW(),
    event_type VARCHAR(100) NOT NULL,     -- 'credential_issued', 'permission_revoked'
    actor VARCHAR(255),                    -- Who performed action
    target VARCHAR(255),                   -- Who was affected
    details JSONB DEFAULT '{}',
    ip_address INET,
    user_agent TEXT
);

-- Indexes
CREATE INDEX idx_permission_instances_email ON permission_instances(email);
CREATE INDEX idx_permission_instances_credential ON permission_instances(credential_did);
CREATE INDEX idx_permission_instances_active ON permission_instances(email) WHERE revoked_at IS NULL;
CREATE INDEX idx_audit_log_timestamp ON iam_audit_log(timestamp DESC);
CREATE INDEX idx_audit_log_event ON iam_audit_log(event_type);
```

**Deliverable:** Run migration on production DB

---

#### Day 3-4: Permission Management API

```python
# api/iam_permissions.py (NEW FILE)

from flask import Blueprint, request, jsonify
from auth.decorators import require_admin_credential
from api.database import get_db_connection
from api.audit_log import log_audit_event
import json
from datetime import datetime

iam_permissions_bp = Blueprint('iam_permissions', __name__)

# ============================================
# PERMISSION TYPE MANAGEMENT
# ============================================

@iam_permissions_bp.route('/api/iam/permission-types', methods=['GET'])
@require_admin_credential
def list_permission_types():
    """
    List all permission types for this site
    GET /api/iam/permission-types?type=role&active=true
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Build query with filters
        query = """
            SELECT id, name, type, description, config, created_at, created_by, active,
                   (SELECT COUNT(*) FROM permission_instances 
                    WHERE permission_type_id = permission_types.id 
                    AND revoked_at IS NULL) as active_instances
            FROM permission_types
            WHERE site_id = %s
        """
        params = [request.site_id]
        
        # Optional filters
        if request.args.get('type'):
            query += " AND type = %s"
            params.append(request.args.get('type'))
            
        if request.args.get('active'):
            query += " AND active = %s"
            params.append(request.args.get('active') == 'true')
        
        query += " ORDER BY created_at DESC"
        
        cursor.execute(query, params)
        results = cursor.fetchall()
        
        permission_types = []
        for row in results:
            permission_types.append({
                'id': row[0],
                'name': row[1],
                'type': row[2],
                'description': row[3],
                'config': row[4],
                'created_at': row[5].isoformat(),
                'created_by': row[6],
                'active': row[7],
                'active_instances': row[8]
            })
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'permission_types': permission_types,
            'count': len(permission_types)
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@iam_permissions_bp.route('/api/iam/permission-types', methods=['POST'])
@require_admin_credential
def create_permission_type():
    """
    Create a new permission type
    POST /api/iam/permission-types
    {
        "name": "premium_tier_1",
        "type": "time-bound",
        "description": "Premium subscription tier 1",
        "config": {
            "duration_days": 365,
            "auto_renew": false
        }
    }
    """
    try:
        data = request.get_json()
        
        # Validate required fields
        if not data.get('name') or not data.get('type'):
            return jsonify({
                'success': False,
                'error': 'Missing required fields: name, type'
            }), 400
        
        # Validate permission type
        valid_types = ['role', 'scope', 'time-bound', 'attribute', 'hierarchical']
        if data['type'] not in valid_types:
            return jsonify({
                'success': False,
                'error': f'Invalid type. Must be one of: {valid_types}'
            }), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Insert permission type
        cursor.execute("""
            INSERT INTO permission_types (name, type, description, config, created_by, site_id)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            data['name'],
            data['type'],
            data.get('description', ''),
            json.dumps(data.get('config', {})),
            request.admin_email,
            request.site_id
        ))
        
        permission_type_id = cursor.fetchone()[0]
        conn.commit()
        
        # Log audit event
        log_audit_event(
            event_type='permission_type_created',
            actor=request.admin_email,
            target=data['name'],
            details={
                'permission_type_id': permission_type_id,
                'type': data['type']
            },
            ip_address=request.remote_addr
        )
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'permission_type_id': permission_type_id,
            'message': f'Permission type "{data["name"]}" created'
        })
        
    except Exception as e:
        if 'duplicate key value violates unique constraint' in str(e):
            return jsonify({
                'success': False,
                'error': f'Permission type "{data["name"]}" already exists'
            }), 400
        return jsonify({'success': False, 'error': str(e)}), 500


@iam_permissions_bp.route('/api/iam/permission-types/<int:type_id>', methods=['PUT'])
@require_admin_credential
def update_permission_type(type_id):
    """
    Update permission type
    PUT /api/iam/permission-types/123
    """
    try:
        data = request.get_json()
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Build update query
        update_fields = []
        params = []
        
        if 'description' in data:
            update_fields.append('description = %s')
            params.append(data['description'])
            
        if 'config' in data:
            update_fields.append('config = %s')
            params.append(json.dumps(data['config']))
            
        if 'active' in data:
            update_fields.append('active = %s')
            params.append(data['active'])
        
        if not update_fields:
            return jsonify({'success': False, 'error': 'No fields to update'}), 400
        
        params.extend([type_id, request.site_id])
        
        cursor.execute(f"""
            UPDATE permission_types
            SET {', '.join(update_fields)}
            WHERE id = %s AND site_id = %s
            RETURNING name
        """, params)
        
        result = cursor.fetchone()
        if not result:
            return jsonify({'success': False, 'error': 'Permission type not found'}), 404
        
        conn.commit()
        
        log_audit_event(
            event_type='permission_type_updated',
            actor=request.admin_email,
            target=result[0],
            details={'permission_type_id': type_id, 'changes': data},
            ip_address=request.remote_addr
        )
        
        cursor.close()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Permission type updated'})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================
# PERMISSION INSTANCE MANAGEMENT
# ============================================

@iam_permissions_bp.route('/api/iam/permissions/grant', methods=['POST'])
@require_admin_credential
def grant_permission():
    """
    Grant permission to a user
    POST /api/iam/permissions/grant
    {
        "email": "user@example.com",
        "permission": "premium_tier_1",
        "expires_at": "2025-12-31T23:59:59Z",  // Optional
        "metadata": {
            "reason": "Annual subscription",
            "order_id": "ORD-12345"
        }
    }
    """
    try:
        data = request.get_json()
        
        if not data.get('email') or not data.get('permission'):
            return jsonify({
                'success': False,
                'error': 'Missing required fields: email, permission'
            }), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get permission type
        cursor.execute("""
            SELECT id, type, config FROM permission_types
            WHERE name = %s AND site_id = %s AND active = true
        """, (data['permission'], request.site_id))
        
        perm_type = cursor.fetchone()
        if not perm_type:
            return jsonify({
                'success': False,
                'error': f'Permission type "{data["permission"]}" not found'
            }), 404
        
        permission_type_id, perm_type_name, perm_config = perm_type
        
        # Calculate expiry for time-bound permissions
        expires_at = data.get('expires_at')
        if perm_type_name == 'time-bound' and not expires_at:
            # Auto-calculate from config
            duration_days = perm_config.get('duration_days', 365)
            from datetime import timedelta
            expires_at = (datetime.now() + timedelta(days=duration_days)).isoformat()
        
        # Grant permission
        cursor.execute("""
            INSERT INTO permission_instances 
            (permission_type_id, email, granted_by, expires_at, metadata, credential_did)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            permission_type_id,
            data['email'],
            request.admin_email,
            expires_at,
            json.dumps(data.get('metadata', {})),
            f'pending_{data["email"]}'  # Placeholder until credential issued
        ))
        
        instance_id = cursor.fetchone()[0]
        conn.commit()
        
        log_audit_event(
            event_type='permission_granted',
            actor=request.admin_email,
            target=data['email'],
            details={
                'permission': data['permission'],
                'instance_id': instance_id,
                'expires_at': expires_at
            },
            ip_address=request.remote_addr
        )
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'instance_id': instance_id,
            'message': f'Permission "{data["permission"]}" granted to {data["email"]}'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@iam_permissions_bp.route('/api/iam/permissions/revoke', methods=['POST'])
@require_admin_credential
def revoke_permission():
    """
    Revoke permission from user
    POST /api/iam/permissions/revoke
    {
        "email": "user@example.com",
        "permission": "premium_tier_1",  // Optional - revoke specific permission
        "reason": "Subscription cancelled"
    }
    """
    try:
        data = request.get_json()
        
        if not data.get('email'):
            return jsonify({'success': False, 'error': 'Missing email'}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Build revocation query
        if data.get('permission'):
            # Revoke specific permission
            cursor.execute("""
                UPDATE permission_instances pi
                SET revoked_at = NOW(),
                    revoked_by = %s,
                    revocation_reason = %s
                FROM permission_types pt
                WHERE pi.permission_type_id = pt.id
                AND pi.email = %s
                AND pt.name = %s
                AND pi.revoked_at IS NULL
                RETURNING pi.id
            """, (request.admin_email, data.get('reason', ''), data['email'], data['permission']))
        else:
            # Revoke ALL permissions
            cursor.execute("""
                UPDATE permission_instances
                SET revoked_at = NOW(),
                    revoked_by = %s,
                    revocation_reason = %s
                WHERE email = %s
                AND revoked_at IS NULL
                RETURNING id
            """, (request.admin_email, data.get('reason', ''), data['email']))
        
        revoked_ids = cursor.fetchall()
        conn.commit()
        
        if not revoked_ids:
            return jsonify({
                'success': False,
                'error': 'No active permissions found to revoke'
            }), 404
        
        log_audit_event(
            event_type='permission_revoked',
            actor=request.admin_email,
            target=data['email'],
            details={
                'permission': data.get('permission', 'ALL'),
                'revoked_count': len(revoked_ids),
                'reason': data.get('reason', '')
            },
            ip_address=request.remote_addr
        )
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'revoked_count': len(revoked_ids),
            'message': f'Revoked {len(revoked_ids)} permission(s) from {data["email"]}'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@iam_permissions_bp.route('/api/iam/users/search', methods=['GET'])
@require_admin_credential
def search_users_by_permission():
    """
    Find all users with specific permission
    GET /api/iam/users/search?permission=admin&active_only=true&limit=50
    """
    try:
        permission = request.args.get('permission')
        active_only = request.args.get('active_only', 'true') == 'true'
        limit = int(request.args.get('limit', 50))
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        query = """
            SELECT pi.email, pt.name, pi.granted_at, pi.expires_at, pi.metadata
            FROM permission_instances pi
            JOIN permission_types pt ON pi.permission_type_id = pt.id
            WHERE pt.site_id = %s
        """
        params = [request.site_id]
        
        if permission:
            query += " AND pt.name = %s"
            params.append(permission)
        
        if active_only:
            query += " AND pi.revoked_at IS NULL"
            query += " AND (pi.expires_at IS NULL OR pi.expires_at > NOW())"
        
        query += " ORDER BY pi.granted_at DESC LIMIT %s"
        params.append(limit)
        
        cursor.execute(query, params)
        results = cursor.fetchall()
        
        users = []
        for row in results:
            users.append({
                'email': row[0],
                'permission': row[1],
                'granted_at': row[2].isoformat(),
                'expires_at': row[3].isoformat() if row[3] else None,
                'metadata': row[4]
            })
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'users': users,
            'count': len(users)
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
```

**Deliverable:** Working REST API for permission management

---

#### Day 5: Audit Logging System

```python
# api/audit_log.py (NEW FILE)

from api.database import get_db_connection
import json
from datetime import datetime

def log_audit_event(event_type, actor, target=None, details=None, ip_address=None, user_agent=None):
    """
    Log an IAM audit event
    
    Args:
        event_type: Type of event (e.g., 'permission_granted', 'credential_issued')
        actor: Who performed the action (email)
        target: Who was affected (email) - optional
        details: Additional event details (dict)
        ip_address: IP address of actor
        user_agent: User agent string
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO iam_audit_log (event_type, actor, target, details, ip_address, user_agent)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            event_type,
            actor,
            target,
            json.dumps(details or {}),
            ip_address,
            user_agent
        ))
        
        conn.commit()
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"❌ Audit log error: {e}")
        # Don't fail the main operation if audit logging fails


def get_audit_log(filters=None, limit=100):
    """
    Retrieve audit log entries
    
    Args:
        filters: Dict of filters (event_type, actor, target, start_date, end_date)
        limit: Max number of entries to return
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        query = "SELECT * FROM iam_audit_log WHERE 1=1"
        params = []
        
        if filters:
            if filters.get('event_type'):
                query += " AND event_type = %s"
                params.append(filters['event_type'])
            
            if filters.get('actor'):
                query += " AND actor = %s"
                params.append(filters['actor'])
            
            if filters.get('target'):
                query += " AND target = %s"
                params.append(filters['target'])
            
            if filters.get('start_date'):
                query += " AND timestamp >= %s"
                params.append(filters['start_date'])
            
            if filters.get('end_date'):
                query += " AND timestamp <= %s"
                params.append(filters['end_date'])
        
        query += " ORDER BY timestamp DESC LIMIT %s"
        params.append(limit)
        
        cursor.execute(query, params)
        results = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return results
        
    except Exception as e:
        print(f"❌ Failed to retrieve audit log: {e}")
        return []
```

**Deliverable:** Audit logging for all IAM operations

---

### Week 2: Dashboard UI

#### Day 6-8: Permission Management Dashboard

```html
<!-- templates/admin/iam_dashboard.html (NEW FILE) -->

{% extends "modern/layout.html" %}

{% block title %}IAM Dashboard - Lemma{% endblock %}

{% block content %}
<div class="iam-dashboard">
    <div class="dashboard-header">
        <h1>IAM Dashboard</h1>
        <p>Manage permissions and user access</p>
    </div>
    
    <!-- Stats Overview -->
    <div class="stats-grid">
        <div class="stat-card">
            <div class="stat-value" id="totalPermissionTypes">-</div>
            <div class="stat-label">Permission Types</div>
        </div>
        <div class="stat-card">
            <div class="stat-value" id="activeUsers">-</div>
            <div class="stat-label">Active Users</div>
        </div>
        <div class="stat-card">
            <div class="stat-value" id="activeInstances">-</div>
            <div class="stat-label">Active Permissions</div>
        </div>
        <div class="stat-card">
            <div class="stat-value" id="expiringSoon">-</div>
            <div class="stat-label">Expiring Soon</div>
        </div>
    </div>
    
    <!-- Tabs -->
    <div class="tabs">
        <button class="tab active" onclick="switchTab('permission-types')">Permission Types</button>
        <button class="tab" onclick="switchTab('users')">Users</button>
        <button class="tab" onclick="switchTab('audit-log')">Audit Log</button>
    </div>
    
    <!-- Permission Types Tab -->
    <div id="tab-permission-types" class="tab-content active">
        <div class="section-header">
            <h2>Permission Types</h2>
            <button class="btn-primary" onclick="showCreatePermissionModal()">
                + Create Permission Type
            </button>
        </div>
        
        <div class="permission-types-list" id="permissionTypesList">
            <!-- Dynamically loaded -->
        </div>
    </div>
    
    <!-- Users Tab -->
    <div id="tab-users" class="tab-content">
        <div class="section-header">
            <h2>Users</h2>
            <div class="search-box">
                <input type="text" id="userSearchInput" placeholder="Search by email or permission...">
                <button onclick="searchUsers()">Search</button>
            </div>
        </div>
        
        <table class="users-table">
            <thead>
                <tr>
                    <th>Email</th>
                    <th>Permissions</th>
                    <th>Last Login</th>
                    <th>Status</th>
                    <th>Actions</th>
                </tr>
            </thead>
            <tbody id="usersTableBody">
                <!-- Dynamically loaded -->
            </tbody>
        </table>
    </div>
    
    <!-- Audit Log Tab -->
    <div id="tab-audit-log" class="tab-content">
        <div class="section-header">
            <h2>Audit Log</h2>
            <select id="auditEventFilter" onchange="loadAuditLog()">
                <option value="">All Events</option>
                <option value="permission_granted">Permission Granted</option>
                <option value="permission_revoked">Permission Revoked</option>
                <option value="permission_type_created">Type Created</option>
            </select>
        </div>
        
        <div class="audit-log" id="auditLogList">
            <!-- Dynamically loaded -->
        </div>
    </div>
</div>

<!-- Create Permission Type Modal -->
<div id="createPermissionModal" class="modal" style="display: none;">
    <div class="modal-content">
        <div class="modal-header">
            <h3>Create Permission Type</h3>
            <button onclick="closeModal('createPermissionModal')">&times;</button>
        </div>
        <div class="modal-body">
            <form id="createPermissionForm">
                <div class="form-group">
                    <label>Permission Name *</label>
                    <input type="text" id="permissionName" required 
                           placeholder="e.g., premium_tier_1, admin, moderator">
                    <small>Use lowercase with underscores</small>
                </div>
                
                <div class="form-group">
                    <label>Permission Type *</label>
                    <select id="permissionType" required onchange="updatePermissionTypeConfig()">
                        <option value="">-- Select Type --</option>
                        <option value="role">Role (simple user roles)</option>
                        <option value="scope">Scope (OAuth-style permissions)</option>
                        <option value="time-bound">Time-Bound (expires after duration)</option>
                        <option value="attribute">Attribute (key-value pairs)</option>
                    </select>
                </div>
                
                <div class="form-group">
                    <label>Description</label>
                    <textarea id="permissionDescription" rows="3"
                              placeholder="Describe what this permission grants access to"></textarea>
                </div>
                
                <!-- Time-bound specific config -->
                <div id="timeBoundConfig" class="form-group" style="display: none;">
                    <label>Duration (days)</label>
                    <input type="number" id="durationDays" value="365" min="1">
                </div>
                
                <div class="form-actions">
                    <button type="button" class="btn-secondary" onclick="closeModal('createPermissionModal')">
                        Cancel
                    </button>
                    <button type="submit" class="btn-primary">
                        Create Permission Type
                    </button>
                </div>
            </form>
        </div>
    </div>
</div>

<style>
.iam-dashboard {
    max-width: 1200px;
    margin: 0 auto;
    padding: 40px 20px;
}

.dashboard-header {
    margin-bottom: 32px;
}

.dashboard-header h1 {
    font-size: 2rem;
    font-weight: 600;
    color: var(--gray-900);
    margin-bottom: 8px;
}

.dashboard-header p {
    color: var(--gray-600);
}

.stats-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 20px;
    margin-bottom: 32px;
}

.stat-card {
    background: var(--white);
    border: 1px solid var(--gray-200);
    border-radius: 12px;
    padding: 24px;
    text-align: center;
}

.stat-value {
    font-size: 2.5rem;
    font-weight: 700;
    color: var(--primary);
    margin-bottom: 8px;
}

.stat-label {
    font-size: 0.9rem;
    color: var(--gray-600);
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

.tabs {
    border-bottom: 2px solid var(--gray-200);
    margin-bottom: 32px;
}

.tab {
    background: none;
    border: none;
    padding: 12px 24px;
    font-size: 1rem;
    color: var(--gray-600);
    cursor: pointer;
    border-bottom: 2px solid transparent;
    margin-bottom: -2px;
    transition: all 0.2s;
}

.tab:hover {
    color: var(--primary);
}

.tab.active {
    color: var(--primary);
    border-bottom-color: var(--primary);
    font-weight: 600;
}

.tab-content {
    display: none;
}

.tab-content.active {
    display: block;
}

.section-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 24px;
}

.section-header h2 {
    font-size: 1.5rem;
    font-weight: 600;
    color: var(--gray-900);
}

.permission-types-list {
    display: grid;
    gap: 16px;
}

.permission-type-card {
    background: var(--white);
    border: 1px solid var(--gray-200);
    border-radius: 12px;
    padding: 20px;
    display: flex;
    justify-content: space-between;
    align-items: start;
}

.permission-type-info h3 {
    font-size: 1.1rem;
    font-weight: 600;
    color: var(--gray-900);
    margin-bottom: 4px;
}

.permission-type-meta {
    font-size: 0.9rem;
    color: var(--gray-600);
    margin-bottom: 8px;
}

.permission-type-stats {
    display: flex;
    gap: 16px;
    margin-top: 12px;
}

.stat-badge {
    background: var(--gray-100);
    padding: 4px 12px;
    border-radius: 6px;
    font-size: 0.85rem;
    color: var(--gray-700);
}

.permission-type-actions {
    display: flex;
    gap: 8px;
}

.modal {
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background: rgba(0, 0, 0, 0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
}

.modal-content {
    background: var(--white);
    border-radius: 12px;
    max-width: 600px;
    width: 90%;
    max-height: 90vh;
    overflow-y: auto;
}

.modal-header {
    padding: 20px;
    border-bottom: 1px solid var(--gray-200);
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.modal-header h3 {
    font-size: 1.25rem;
    font-weight: 600;
    color: var(--gray-900);
}

.modal-body {
    padding: 20px;
}

.form-group {
    margin-bottom: 20px;
}

.form-group label {
    display: block;
    font-weight: 600;
    color: var(--gray-900);
    margin-bottom: 8px;
}

.form-group input,
.form-group select,
.form-group textarea {
    width: 100%;
    padding: 10px 12px;
    border: 1px solid var(--gray-300);
    border-radius: 6px;
    font-size: 1rem;
}

.form-group small {
    display: block;
    margin-top: 4px;
    font-size: 0.85rem;
    color: var(--gray-600);
}

.form-actions {
    display: flex;
    gap: 12px;
    justify-content: flex-end;
    margin-top: 24px;
}

.search-box {
    display: flex;
    gap: 8px;
}

.search-box input {
    padding: 8px 12px;
    border: 1px solid var(--gray-300);
    border-radius: 6px;
    min-width: 300px;
}

.users-table {
    width: 100%;
    border-collapse: collapse;
    background: var(--white);
    border: 1px solid var(--gray-200);
    border-radius: 12px;
    overflow: hidden;
}

.users-table th {
    background: var(--gray-50);
    padding: 12px 16px;
    text-align: left;
    font-weight: 600;
    color: var(--gray-900);
    border-bottom: 1px solid var(--gray-200);
}

.users-table td {
    padding: 12px 16px;
    border-bottom: 1px solid var(--gray-100);
}

.audit-log {
    background: var(--white);
    border: 1px solid var(--gray-200);
    border-radius: 12px;
    padding: 20px;
}

.audit-entry {
    padding: 12px 0;
    border-bottom: 1px solid var(--gray-100);
}

.audit-entry:last-child {
    border-bottom: none;
}
</style>

<script>
// Load dashboard data
async function loadDashboard() {
    try {
        // Load stats
        const statsResponse = await fetch('/api/iam/stats');
        const stats = await statsResponse.json();
        
        if (stats.success) {
            document.getElementById('totalPermissionTypes').textContent = stats.permission_types || 0;
            document.getElementById('activeUsers').textContent = stats.active_users || 0;
            document.getElementById('activeInstances').textContent = stats.active_instances || 0;
            document.getElementById('expiringSoon').textContent = stats.expiring_soon || 0;
        }
        
        // Load permission types
        await loadPermissionTypes();
        
    } catch (error) {
        console.error('Failed to load dashboard:', error);
    }
}

async function loadPermissionTypes() {
    try {
        const response = await fetch('/api/iam/permission-types');
        const data = await response.json();
        
        if (data.success) {
            const list = document.getElementById('permissionTypesList');
            
            if (data.permission_types.length === 0) {
                list.innerHTML = `
                    <div style="text-align: center; padding: 40px; color: var(--gray-600);">
                        No permission types created yet. Click "Create Permission Type" to get started.
                    </div>
                `;
                return;
            }
            
            list.innerHTML = data.permission_types.map(pt => `
                <div class="permission-type-card">
                    <div class="permission-type-info">
                        <h3>${pt.name}</h3>
                        <div class="permission-type-meta">
                            <span class="type-badge">${pt.type}</span>
                            ${pt.description ? `<span> • ${pt.description}</span>` : ''}
                        </div>
                        <div class="permission-type-stats">
                            <div class="stat-badge">
                                ${pt.active_instances} active users
                            </div>
                            <div class="stat-badge">
                                Created ${new Date(pt.created_at).toLocaleDateString()}
                            </div>
                        </div>
                    </div>
                    <div class="permission-type-actions">
                        <button class="btn-secondary" onclick="grantPermission('${pt.name}')">
                            Grant
                        </button>
                        <button class="btn-secondary" onclick="viewUsers('${pt.name}')">
                            View Users
                        </button>
                    </div>
                </div>
            `).join('');
        }
    } catch (error) {
        console.error('Failed to load permission types:', error);
    }
}

function switchTab(tabName) {
    // Hide all tabs
    document.querySelectorAll('.tab').forEach(tab => tab.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));
    
    // Show selected tab
    event.target.classList.add('active');
    document.getElementById(`tab-${tabName}`).classList.add('active');
    
    // Load tab data
    if (tabName === 'users') loadUsers();
    if (tabName === 'audit-log') loadAuditLog();
}

function showCreatePermissionModal() {
    document.getElementById('createPermissionModal').style.display = 'flex';
}

function closeModal(modalId) {
    document.getElementById(modalId).style.display = 'none';
}

function updatePermissionTypeConfig() {
    const type = document.getElementById('permissionType').value;
    const timeBoundConfig = document.getElementById('timeBoundConfig');
    
    if (type === 'time-bound') {
        timeBoundConfig.style.display = 'block';
    } else {
        timeBoundConfig.style.display = 'none';
    }
}

document.getElementById('createPermissionForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const formData = {
        name: document.getElementById('permissionName').value,
        type: document.getElementById('permissionType').value,
        description: document.getElementById('permissionDescription').value,
        config: {}
    };
    
    if (formData.type === 'time-bound') {
        formData.config.duration_days = parseInt(document.getElementById('durationDays').value);
    }
    
    try {
        const response = await fetch('/api/iam/permission-types', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(formData)
        });
        
        const result = await response.json();
        
        if (result.success) {
            alert(`Permission type "${formData.name}" created successfully!`);
            closeModal('createPermissionModal');
            loadPermissionTypes();
            document.getElementById('createPermissionForm').reset();
        } else {
            alert(`Error: ${result.error}`);
        }
    } catch (error) {
        alert(`Failed to create permission type: ${error.message}`);
    }
});

// Load dashboard on page load
loadDashboard();
</script>
{% endblock %}
```

**Deliverable:** Working dashboard UI for permission management

---

#### Day 9-10: Flask Route Integration + Testing

```python
# app.py (ADD THESE ROUTES)

from api.iam_permissions import iam_permissions_bp

# Register IAM blueprint
app.register_blueprint(iam_permissions_bp)

@app.route('/admin/iam')
@require_admin_credential
def iam_dashboard():
    """IAM Dashboard"""
    return render_template('admin/iam_dashboard.html')

# Stats endpoint for dashboard
@app.route('/api/iam/stats')
@require_admin_credential
def iam_stats():
    """Get IAM statistics"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Count permission types
        cursor.execute("""
            SELECT COUNT(*) FROM permission_types 
            WHERE site_id = %s AND active = true
        """, [request.site_id])
        permission_types = cursor.fetchone()[0]
        
        # Count active users
        cursor.execute("""
            SELECT COUNT(DISTINCT email) FROM permission_instances 
            WHERE revoked_at IS NULL
        """)
        active_users = cursor.fetchone()[0]
        
        # Count active permission instances
        cursor.execute("""
            SELECT COUNT(*) FROM permission_instances 
            WHERE revoked_at IS NULL
            AND (expires_at IS NULL OR expires_at > NOW())
        """)
        active_instances = cursor.fetchone()[0]
        
        # Count expiring soon (next 30 days)
        cursor.execute("""
            SELECT COUNT(*) FROM permission_instances 
            WHERE revoked_at IS NULL
            AND expires_at BETWEEN NOW() AND NOW() + INTERVAL '30 days'
        """)
        expiring_soon = cursor.fetchone()[0]
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'permission_types': permission_types,
            'active_users': active_users,
            'active_instances': active_instances,
            'expiring_soon': expiring_soon
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
```

**Deliverable:** Fully integrated IAM system ready for use

---

## ✅ SPRINT 1 DELIVERABLES:
- ✅ Database schema with 5 tables
- ✅ REST API with 8 endpoints
- ✅ Audit logging system
- ✅ Admin dashboard UI
- ✅ Permission type management
- ✅ Grant/revoke permissions
- ✅ User search by permission

**SHIP TO CUSTOMERS:** After Sprint 1, customers can manage permissions via UI/API!

---

## 🎯 SPRINT 2: POLICIES + BULK OPERATIONS (Weeks 3-4)

### Week 3: Policy Engine

#### Day 11-12: Policy Definition System

```python
# api/permission_policies.py (NEW FILE)

from flask import Blueprint, request, jsonify
from auth.decorators import require_admin_credential
from api.database import get_db_connection
from api.audit_log import log_audit_event
import json
from datetime import datetime

policies_bp = Blueprint('policies', __name__)

class PolicyEvaluator:
    """Evaluate complex permission policies"""
    
    def __init__(self, policy_rules):
        self.rules = policy_rules
    
    def evaluate(self, user_permissions, context=None):
        """
        Evaluate if user meets policy requirements
        
        Args:
            user_permissions: List of permission strings user has
            context: Request context (IP, time, etc.)
            
        Returns:
            {
                'allowed': bool,
                'reason': str,
                'matched_rules': [],
                'failed_rules': []
            }
        """
        result = {
            'allowed': True,
            'reason': '',
            'matched_rules': [],
            'failed_rules': []
        }
        
        # Check REQUIRED permissions (AND logic)
        if 'required' in self.rules:
            for required in self.rules['required']:
                if required not in user_permissions:
                    result['allowed'] = False
                    result['failed_rules'].append({
                        'type': 'required',
                        'permission': required,
                        'reason': f'Missing required permission: {required}'
                    })
                else:
                    result['matched_rules'].append({
                        'type': 'required',
                        'permission': required
                    })
        
        # Check ANY_OF permissions (OR logic)
        if 'any_of' in self.rules and self.rules['any_of']:
            has_any = any(perm in user_permissions for perm in self.rules['any_of'])
            if not has_any:
                result['allowed'] = False
                result['failed_rules'].append({
                    'type': 'any_of',
                    'permissions': self.rules['any_of'],
                    'reason': f'Must have at least one of: {", ".join(self.rules["any_of"])}'
                })
        
        # Check FORBIDDEN permissions (must NOT have)
        if 'forbidden' in self.rules:
            for forbidden in self.rules['forbidden']:
                if forbidden in user_permissions:
                    result['allowed'] = False
                    result['failed_rules'].append({
                        'type': 'forbidden',
                        'permission': forbidden,
                        'reason': f'Forbidden permission present: {forbidden}'
                    })
        
        # Check TIME constraints
        if 'time_valid' in self.rules:
            now = datetime.now()
            
            if 'not_before' in self.rules['time_valid']:
                not_before = datetime.fromisoformat(self.rules['time_valid']['not_before'])
                if now < not_before:
                    result['allowed'] = False
                    result['failed_rules'].append({
                        'type': 'time',
                        'reason': f'Policy not valid until {not_before.isoformat()}'
                    })
            
            if 'not_after' in self.rules['time_valid']:
                not_after = datetime.fromisoformat(self.rules['time_valid']['not_after'])
                if now > not_after:
                    result['allowed'] = False
                    result['failed_rules'].append({
                        'type': 'time',
                        'reason': f'Policy expired on {not_after.isoformat()}'
                    })
        
        # Set summary reason
        if not result['allowed']:
            reasons = [rule['reason'] for rule in result['failed_rules']]
            result['reason'] = '; '.join(reasons)
        else:
            result['reason'] = 'All policy requirements met'
        
        return result


@policies_bp.route('/api/iam/policies', methods=['POST'])
@require_admin_credential
def create_policy():
    """
    Create permission policy
    POST /api/iam/policies
    {
        "name": "content_moderator",
        "description": "Can moderate user content",
        "rules": {
            "required": ["role:moderator"],
            "any_of": ["scope:delete:comments", "scope:ban:users"],
            "forbidden": ["status:suspended"],
            "time_valid": {
                "not_before": "2025-01-01T00:00:00Z",
                "not_after": "2025-12-31T23:59:59Z"
            }
        }
    }
    """
    try:
        data = request.get_json()
        
        if not data.get('name') or not data.get('rules'):
            return jsonify({
                'success': False,
                'error': 'Missing required fields: name, rules'
            }), 400
        
        # Validate policy rules
        evaluator = PolicyEvaluator(data['rules'])
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO permission_policies (name, description, rules, site_id)
            VALUES (%s, %s, %s, %s)
            RETURNING id
        """, (
            data['name'],
            data.get('description', ''),
            json.dumps(data['rules']),
            request.site_id
        ))
        
        policy_id = cursor.fetchone()[0]
        conn.commit()
        
        log_audit_event(
            event_type='policy_created',
            actor=request.admin_email,
            target=data['name'],
            details={'policy_id': policy_id, 'rules': data['rules']},
            ip_address=request.remote_addr
        )
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'policy_id': policy_id,
            'message': f'Policy "{data["name"]}" created'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@policies_bp.route('/api/iam/policies/<policy_name>/evaluate', methods='POST'])
def evaluate_policy(policy_name):
    """
    Evaluate if user meets policy requirements
    POST /api/iam/policies/content_moderator/evaluate
    {
        "user_permissions": ["role:moderator", "scope:delete:comments"],
        "context": {
            "ip": "192.168.1.1",
            "time": "2025-10-28T10:00:00Z"
        }
    }
    """
    try:
        data = request.get_json()
        
        # Get policy
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT rules FROM permission_policies
            WHERE name = %s AND site_id = %s AND active = true
        """, (policy_name, request.site_id))
        
        result = cursor.fetchone()
        if not result:
            return jsonify({
                'success': False,
                'error': f'Policy "{policy_name}" not found'
            }), 404
        
        policy_rules = result[0]
        
        # Evaluate policy
        evaluator = PolicyEvaluator(policy_rules)
        evaluation = evaluator.evaluate(
            data.get('user_permissions', []),
            data.get('context')
        )
        
        # Log evaluation
        log_audit_event(
            event_type='policy_evaluated',
            actor=data.get('email', 'unknown'),
            target=policy_name,
            details={
                'allowed': evaluation['allowed'],
                'reason': evaluation['reason']
            },
            ip_address=request.remote_addr
        )
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'policy': policy_name,
            'evaluation': evaluation
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
```

**Deliverable:** Policy engine with complex permission logic

---

#### Day 13-14: Bulk Operations

```python
# api/bulk_operations.py (NEW FILE)

from flask import Blueprint, request, jsonify
from auth.decorators import require_admin_credential
from api.database import get_db_connection
from api.audit_log import log_audit_event
import csv
import io
import json

bulk_bp = Blueprint('bulk', __name__)

@bulk_bp.route('/api/iam/bulk/grant-permissions', methods=['POST'])
@require_admin_credential
def bulk_grant_permissions():
    """
    Bulk grant permissions from CSV
    POST /api/iam/bulk/grant-permissions
    Content-Type: multipart/form-data
    
    CSV Format:
    email,permission,expires_at,metadata
    user1@example.com,premium_tier_1,2025-12-31,"{\"reason\":\"annual\"}"
    user2@example.com,admin,,"{\"department\":\"engineering\"}"
    """
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file uploaded'}), 400
        
        file = request.files['file']
        if not file.filename.endswith('.csv'):
            return jsonify({'success': False, 'error': 'File must be CSV'}), 400
        
        # Read CSV
        content = file.read().decode('utf-8')
        csv_reader = csv.DictReader(io.StringIO(content))
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        results = {
            'success': [],
            'failed': [],
            'total': 0
        }
        
        for row in csv_reader:
            results['total'] += 1
            
            try:
                email = row['email'].strip()
                permission = row['permission'].strip()
                expires_at = row.get('expires_at', '').strip() or None
                metadata = json.loads(row.get('metadata', '{}'))
                
                # Get permission type
                cursor.execute("""
                    SELECT id FROM permission_types
                    WHERE name = %s AND site_id = %s AND active = true
                """, (permission, request.site_id))
                
                perm_type = cursor.fetchone()
                if not perm_type:
                    results['failed'].append({
                        'email': email,
                        'permission': permission,
                        'reason': f'Permission type "{permission}" not found'
                    })
                    continue
                
                # Grant permission
                cursor.execute("""
                    INSERT INTO permission_instances 
                    (permission_type_id, email, granted_by, expires_at, metadata, credential_did)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (
                    perm_type[0],
                    email,
                    request.admin_email,
                    expires_at,
                    json.dumps(metadata),
                    f'pending_{email}'
                ))
                
                results['success'].append({
                    'email': email,
                    'permission': permission
                })
                
            except Exception as e:
                results['failed'].append({
                    'email': row.get('email', 'unknown'),
                    'permission': row.get('permission', 'unknown'),
                    'reason': str(e)
                })
        
        conn.commit()
        
        log_audit_event(
            event_type='bulk_permissions_granted',
            actor=request.admin_email,
            details={
                'total': results['total'],
                'success': len(results['success']),
                'failed': len(results['failed'])
            },
            ip_address=request.remote_addr
        )
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'results': results
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@bulk_bp.route('/api/iam/bulk/revoke-permissions', methods=['POST'])
@require_admin_credential
def bulk_revoke_permissions():
    """
    Bulk revoke permissions
    POST /api/iam/bulk/revoke-permissions
    {
        "emails": ["user1@example.com", "user2@example.com"],
        "permission": "premium_tier_1",  // Optional - revoke specific permission
        "reason": "Subscription expired"
    }
    """
    try:
        data = request.get_json()
        
        if not data.get('emails'):
            return jsonify({'success': False, 'error': 'Missing emails list'}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        results = {
            'success': [],
            'failed': [],
            'total': len(data['emails'])
        }
        
        for email in data['emails']:
            try:
                if data.get('permission'):
                    # Revoke specific permission
                    cursor.execute("""
                        UPDATE permission_instances pi
                        SET revoked_at = NOW(),
                            revoked_by = %s,
                            revocation_reason = %s
                        FROM permission_types pt
                        WHERE pi.permission_type_id = pt.id
                        AND pi.email = %s
                        AND pt.name = %s
                        AND pi.revoked_at IS NULL
                        RETURNING pi.id
                    """, (request.admin_email, data.get('reason', ''), email, data['permission']))
                else:
                    # Revoke ALL permissions
                    cursor.execute("""
                        UPDATE permission_instances
                        SET revoked_at = NOW(),
                            revoked_by = %s,
                            revocation_reason = %s
                        WHERE email = %s
                        AND revoked_at IS NULL
                        RETURNING id
                    """, (request.admin_email, data.get('reason', ''), email))
                
                revoked = cursor.fetchall()
                if revoked:
                    results['success'].append({
                        'email': email,
                        'revoked_count': len(revoked)
                    })
                else:
                    results['failed'].append({
                        'email': email,
                        'reason': 'No active permissions found'
                    })
                    
            except Exception as e:
                results['failed'].append({
                    'email': email,
                    'reason': str(e)
                })
        
        conn.commit()
        
        log_audit_event(
            event_type='bulk_permissions_revoked',
            actor=request.admin_email,
            details={
                'total': results['total'],
                'success': len(results['success']),
                'failed': len(results['failed']),
                'reason': data.get('reason', '')
            },
            ip_address=request.remote_addr
        )
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'results': results
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
```

**Deliverable:** Bulk operations for scaling permission management

---

### Week 4: User Management + Analytics

#### Day 15-16: User Profile System

```python
# api/user_profiles.py (NEW FILE)

from flask import Blueprint, request, jsonify
from auth.decorators import require_admin_credential
from api.database import get_db_connection
import json
from datetime import datetime

profiles_bp = Blueprint('profiles', __name__)

@profiles_bp.route('/api/iam/users/<email>', methods=['GET'])
@require_admin_credential
def get_user_profile(email):
    """
    Get complete user profile
    GET /api/iam/users/user@example.com
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get user profile
        cursor.execute("""
            SELECT id, email, display_name, avatar_url, created_at, last_login, metadata
            FROM iam_user_profiles
            WHERE email = %s
        """, [email])
        
        profile = cursor.fetchone()
        if not profile:
            # Create profile on first access
            cursor.execute("""
                INSERT INTO iam_user_profiles (email)
                VALUES (%s)
                RETURNING id, email, display_name, avatar_url, created_at, last_login, metadata
            """, [email])
            profile = cursor.fetchone()
            conn.commit()
        
        # Get active permissions
        cursor.execute("""
            SELECT pt.name, pt.type, pi.granted_at, pi.expires_at, pi.metadata
            FROM permission_instances pi
            JOIN permission_types pt ON pi.permission_type_id = pt.id
            WHERE pi.email = %s
            AND pi.revoked_at IS NULL
            AND (pi.expires_at IS NULL OR pi.expires_at > NOW())
        """, [email])
        
        permissions = []
        for row in cursor.fetchall():
            permissions.append({
                'name': row[0],
                'type': row[1],
                'granted_at': row[2].isoformat(),
                'expires_at': row[3].isoformat() if row[3] else None,
                'metadata': row[4]
            })
        
        # Get permission history
        cursor.execute("""
            SELECT pt.name, pi.granted_at, pi.revoked_at, pi.granted_by, pi.revoked_by
            FROM permission_instances pi
            JOIN permission_types pt ON pi.permission_type_id = pt.id
            WHERE pi.email = %s
            ORDER BY pi.granted_at DESC
            LIMIT 50
        """, [email])
        
        history = []
        for row in cursor.fetchall():
            history.append({
                'permission': row[0],
                'granted_at': row[1].isoformat(),
                'revoked_at': row[2].isoformat() if row[2] else None,
                'granted_by': row[3],
                'revoked_by': row[4]
            })
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'profile': {
                'id': profile[0],
                'email': profile[1],
                'display_name': profile[2],
                'avatar_url': profile[3],
                'created_at': profile[4].isoformat(),
                'last_login': profile[5].isoformat() if profile[5] else None,
                'metadata': profile[6],
                'permissions': permissions,
                'history': history
            }
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
```

**Deliverable:** Complete user profile system

---

#### Day 17-18: Analytics Dashboard

```python
# api/iam_analytics.py (NEW FILE)

from flask import Blueprint, request, jsonify
from auth.decorators import require_admin_credential
from api.database import get_db_connection
from datetime import datetime, timedelta

analytics_bp = Blueprint('analytics', __name__)

@analytics_bp.route('/api/iam/analytics/overview', methods=['GET'])
@require_admin_credential
def analytics_overview():
    """
    Get IAM analytics overview
    GET /api/iam/analytics/overview?days=30
    """
    try:
        days = int(request.args.get('days', 30))
        start_date = datetime.now() - timedelta(days=days)
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Permissions granted over time
        cursor.execute("""
            SELECT DATE(granted_at) as date, COUNT(*) as count
            FROM permission_instances
            WHERE granted_at >= %s
            GROUP BY DATE(granted_at)
            ORDER BY date
        """, [start_date])
        
        granted_over_time = [
            {'date': row[0].isoformat(), 'count': row[1]}
            for row in cursor.fetchall()
        ]
        
        # Top permissions by user count
        cursor.execute("""
            SELECT pt.name, COUNT(DISTINCT pi.email) as user_count
            FROM permission_instances pi
            JOIN permission_types pt ON pi.permission_type_id = pt.id
            WHERE pi.revoked_at IS NULL
            GROUP BY pt.name
            ORDER BY user_count DESC
            LIMIT 10
        """)
        
        top_permissions = [
            {'permission': row[0], 'users': row[1]}
            for row in cursor.fetchall()
        ]
        
        # Permission type distribution
        cursor.execute("""
            SELECT pt.type, COUNT(*) as count
            FROM permission_instances pi
            JOIN permission_types pt ON pi.permission_type_id = pt.id
            WHERE pi.revoked_at IS NULL
            GROUP BY pt.type
        """)
        
        type_distribution = [
            {'type': row[0], 'count': row[1]}
            for row in cursor.fetchall()
        ]
        
        # Recent activity
        cursor.execute("""
            SELECT event_type, COUNT(*) as count
            FROM iam_audit_log
            WHERE timestamp >= %s
            GROUP BY event_type
            ORDER BY count DESC
        """, [start_date])
        
        activity = [
            {'event': row[0], 'count': row[1]}
            for row in cursor.fetchall()
        ]
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'analytics': {
                'granted_over_time': granted_over_time,
                'top_permissions': top_permissions,
                'type_distribution': type_distribution,
                'activity': activity
            }
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
```

**Deliverable:** Analytics dashboard with insights

---

## ✅ SPRINT 2 DELIVERABLES:
- ✅ Policy engine with complex rules
- ✅ Policy evaluation endpoint
- ✅ Bulk grant permissions (CSV upload)
- ✅ Bulk revoke permissions
- ✅ User profile system
- ✅ Analytics dashboard
- ✅ Permission history tracking

**SHIP TO CUSTOMERS:** Full-featured IAM platform!

---

## 🎯 SPRINT 3: DEVELOPER EXPERIENCE (Weeks 5-6)

### Week 5: SDKs + Documentation

#### Day 19-21: Node.js SDK

```javascript
// @lemma/iam-sdk-node/index.js (NEW PACKAGE)

const axios = require('axios');

class LemmaIAM {
    constructor(config) {
        this.apiKey = config.apiKey;
        this.baseUrl = config.baseUrl || 'https://lemma.id';
        this.client = axios.create({
            baseURL: this.baseUrl,
            headers: {
                'Authorization': `Bearer ${this.apiKey}`,
                'Content-Type': 'application/json'
            }
        });
    }
    
    // Permission Types
    async createPermissionType(data) {
        const response = await this.client.post('/api/iam/permission-types', data);
        return response.data;
    }
    
    async listPermissionTypes(filters = {}) {
        const response = await this.client.get('/api/iam/permission-types', { params: filters });
        return response.data;
    }
    
    // Permissions
    async grantPermission(email, permission, options = {}) {
        const response = await this.client.post('/api/iam/permissions/grant', {
            email,
            permission,
            ...options
        });
        return response.data;
    }
    
    async revokePermission(email, permission, reason) {
        const response = await this.client.post('/api/iam/permissions/revoke', {
            email,
            permission,
            reason
        });
        return response.data;
    }
    
    // Policies
    async evaluatePolicy(policyName, userPermissions, context) {
        const response = await this.client.post(`/api/iam/policies/${policyName}/evaluate`, {
            user_permissions: userPermissions,
            context
        });
        return response.data;
    }
    
    // Express Middleware
    requirePermission(permission) {
        return async (req, res, next) => {
            try {
                const credential = req.headers['x-lemma-credential'];
                if (!credential) {
                    return res.status(401).json({ error: 'No credential provided' });
                }
                
                // Verify credential has permission
                // (integrate with verification API)
                
                next();
            } catch (error) {
                res.status(403).json({ error: 'Permission denied' });
            }
        };
    }
}

module.exports = LemmaIAM;
```

**Deliverable:** Production-ready Node.js SDK

---

#### Day 22-24: Python SDK

```python
# lemma-iam-sdk-python/lemma_iam/__init__.py (NEW PACKAGE)

import requests
from typing import List, Dict, Optional
from functools import wraps

class LemmaIAM:
    def __init__(self, api_key: str, base_url: str = 'https://lemma.id'):
        self.api_key = api_key
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        })
    
    def create_permission_type(self, name: str, type: str, **kwargs) -> Dict:
        """Create new permission type"""
        response = self.session.post(
            f'{self.base_url}/api/iam/permission-types',
            json={'name': name, 'type': type, **kwargs}
        )
        response.raise_for_status()
        return response.json()
    
    def grant_permission(self, email: str, permission: str, **kwargs) -> Dict:
        """Grant permission to user"""
        response = self.session.post(
            f'{self.base_url}/api/iam/permissions/grant',
            json={'email': email, 'permission': permission, **kwargs}
        )
        response.raise_for_status()
        return response.json()
    
    def revoke_permission(self, email: str, permission: str = None, reason: str = '') -> Dict:
        """Revoke permission from user"""
        response = self.session.post(
            f'{self.base_url}/api/iam/permissions/revoke',
            json={'email': email, 'permission': permission, 'reason': reason}
        )
        response.raise_for_status()
        return response.json()
    
    # Flask/FastAPI Decorator
    def require_permission(self, permission: str):
        """Decorator to require permission for route"""
        def decorator(f):
            @wraps(f)
            def decorated_function(*args, **kwargs):
                # Get credential from request
                # Verify permission
                # Call original function if authorized
                return f(*args, **kwargs)
            return decorated_function
        return decorator

# Example usage:
# lemma = LemmaIAM(api_key=os.environ['LEMMA_API_KEY'])
#
# @app.route('/admin')
# @lemma.require_permission('role:admin')
# def admin_dashboard():
#     return render_template('admin.html')
```

**Deliverable:** Production-ready Python SDK

---

### Week 6: Documentation + Examples

#### Day 25-27: Developer Documentation

Create comprehensive docs at `docs/IAM_DEVELOPER_GUIDE.md`:

1. **Quick Start Guide**
2. **API Reference**
3. **SDK Documentation**
4. **Code Examples**
5. **Best Practices**
6. **Migration Guides**

---

#### Day 28-30: Example Applications

Build 3 reference implementations:

1. **Express.js App** with Lemma IAM
2. **Flask App** with Lemma IAM
3. **React Dashboard** for permission management

---

## ✅ SPRINT 3 DELIVERABLES:
- ✅ Node.js SDK (published to NPM)
- ✅ Python SDK (published to PyPI)
- ✅ Complete developer documentation
- ✅ 3 example applications
- ✅ Migration guides from Auth0/Clerk

**SHIP TO CUSTOMERS:** Full developer platform!

---

## 📊 FINAL DELIVERABLES (After 6 Weeks):

### ✅ DATABASE LAYER:
- Permission types table
- Permission instances table
- Permission policies table
- User profiles table
- Audit log table

### ✅ API LAYER:
- 15+ REST endpoints
- Policy evaluation engine
- Bulk operations
- Analytics endpoints

### ✅ UI LAYER:
- Admin dashboard
- Permission management
- User search
- Audit log viewer
- Analytics charts

### ✅ SDK LAYER:
- Node.js SDK
- Python SDK
- Express middleware
- Flask decorators

### ✅ DOCUMENTATION:
- Developer guide
- API reference
- Code examples
- Migration guides

---

## 🎯 SUCCESS METRICS:

After 6 weeks, you can say:

**"Lemma IAM is a complete OAuth alternative with:**
- ✅ 18µs verification (10,000x faster than Auth0)
- ✅ $0 per verification (vs $0.001-0.01)
- ✅ Full permission management
- ✅ Policy engine
- ✅ Audit logging
- ✅ Developer SDKs
- ✅ Analytics dashboard"

**Ready to compete with Auth0, Clerk, and WorkOS!** 🚀

---

## 💰 PRICING AFTER COMPLETION:

**Free Tier:**
- 1,000 users
- Basic permissions
- Community support

**Professional ($99/mo):**
- Unlimited users
- Advanced policies
- Bulk operations
- Email support

**Enterprise ($499/mo):**
- Everything
- Custom policies
- Audit exports
- SLA + dedicated support

---

**Want me to start building Sprint 1 Week 1 (Days 1-2: Database Schema)?**

