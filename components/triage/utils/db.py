from sqlalchemy import (
    Column,
    Integer,
    NullPool,
    String,
    BigInteger,
    Boolean,
    Text,
    ForeignKey,
    UniqueConstraint,
    create_engine,
    func,
    Float,
)
from sqlalchemy.orm import relationship, declarative_base, sessionmaker
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, ENUM
from typing import List

# Create the declarative base class
Base = declarative_base()

# Define PostgreSQL ENUM types
TaskTypeEnum = ENUM('full', 'delta', name='tasktypeenum')
TaskStatusEnum = ENUM('canceled', 'errored', 'pending', 'processing',
                      'succeeded', 'failed', 'waiting', name='taskstatusenum')
SourceTypeEnum = ENUM('repo', 'fuzz_tooling', 'diff', name='sourcetypeenum')
FuzzerTypeEnum = ENUM('seedgen', 'prime', 'general', 'directed', 'corpus', name='fuzzertypeenum')

# CRS basic tables


class User(Base):
    __tablename__ = 'users'
    # serial maps to auto-incrementing Integer
    id = Column(Integer, primary_key=True)
    username = Column(String, nullable=False, unique=True)
    password = Column(String, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())


class Message(Base):
    __tablename__ = 'messages'
    id = Column(String, primary_key=True)
    message_time = Column(BigInteger, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())


class Task(Base):
    __tablename__ = 'tasks'
    id = Column(String, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    message_id = Column(String, ForeignKey('messages.id'), nullable=False)
    deadline = Column(BigInteger, nullable=False)
    focus = Column(String, nullable=False)
    project_name = Column(String, nullable=False)
    task_type = Column(TaskTypeEnum, nullable=False)
    status = Column(TaskStatusEnum, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    metadata_ = Column("metadata", JSONB)

    # Relationships
    user = relationship('User')
    message = relationship('Message')


class Source(Base):
    __tablename__ = 'sources'
    id = Column(Integer, primary_key=True)
    task_id = Column(String, ForeignKey('tasks.id'), nullable=False)
    sha256 = Column(String(64), nullable=False)  # varchar(64) specifies length
    source_type = Column(SourceTypeEnum, nullable=False)
    url = Column(String, nullable=False)
    path = Column(String)  # varchar without length maps to String

    # Relationship
    task = relationship('Task')

# Component specific tables


class Bug(Base):
    __tablename__ = 'bugs'
    id = Column(Integer, primary_key=True)
    task_id = Column(String, ForeignKey('tasks.id'), nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    architecture = Column(String, nullable=False)
    poc = Column(String, nullable=False)  # text maps to String
    harness_name = Column(String, nullable=False)  # text maps to String
    sanitizer = Column(String, nullable=False)
    sarif_report = Column(JSONB)

    # Relationship
    task = relationship('Task')


class BugProfile(Base):
    __tablename__ = 'bug_profiles'
    id = Column(Integer, primary_key=True)
    task_id = Column(String, ForeignKey('tasks.id'), nullable=False)
    harness_name = Column(String, nullable=False)  # text maps to String
    sanitizer_bug_type = Column(String, nullable=False)  # text maps to String
    trigger_point = Column(String, nullable=False)  # text maps to String
    summary = Column(String, nullable=False)  # text maps to String
    sanitizer = Column(String, nullable=False)

    # Relationship
    task = relationship('Task')


class BugGroup(Base):
    __tablename__ = 'bug_groups'
    id = Column(Integer, primary_key=True)
    bug_id = Column(Integer, ForeignKey('bugs.id'), nullable=False)
    bug_profile_id = Column(Integer, ForeignKey(
        'bug_profiles.id'), nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    diff_only = Column(Boolean, nullable=True)

    # Unique constraint
    __table_args__ = (UniqueConstraint('bug_id', 'bug_profile_id'),)


class BugCluster(Base):
    __tablename__ = 'bug_clusters'
    id = Column(Integer, primary_key=True)
    task_id = Column(String, ForeignKey('tasks.id'), nullable=False)
    trigger_point = Column(String, nullable=False)  # text maps to String

    # Relationship
    task = relationship('Task')


class BugClusterGroup(Base):
    __tablename__ = 'bug_cluster_groups'
    id = Column(Integer, primary_key=True)
    bug_profile_id = Column(Integer, ForeignKey(
        'bug_profiles.id'), nullable=False)
    bug_cluster_id = Column(Integer, ForeignKey(
        'bug_clusters.id'), nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    # Unique constraint
    __table_args__ = (UniqueConstraint('bug_profile_id', 'bug_cluster_id'),)


def connect_database(database_url):
    engine = create_engine(database_url, poolclass=NullPool)

    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


def query_for_crash(bug_profile_id: int, database_url: str = None) -> str:
    """
    Query the database for the summary of a bug profile with the given ID.

    Args:
        bug_profile_id: The ID of the bug profile to query
        database_url: Optional database URL (if not provided, uses the global one)

    Returns:
        The summary of the bug profile, or None if not found
    """

    db_session = connect_database(database_url)

    try:
        # Query the bug_profiles table for the summary column
        bug_profile = db_session.query(BugProfile).filter(
            BugProfile.id == bug_profile_id
        ).first()

        if bug_profile:
            return bug_profile.summary
        else:
            print(f"[!] No bug profile found with ID {bug_profile_id}")
            return None

    except Exception as e:
        print(f"[!] Error querying bug profile {bug_profile_id}: {e}")
        return None
    finally:
        db_session.close()


def query_for_profiles(task_id: str, database_url: str = None) -> List[BugProfile]:
    """
    Query the database for all bug profiles associated with a specific task ID
    that are already associated with a bug cluster.

    Args:
        task_id: The ID of the task to query profiles for
        database_url: Optional database URL (if not provided, uses the global one)

    Returns:
        A list of BugProfile objects associated with the task and a cluster, or empty list if none found
    """

    db_session = connect_database(database_url)

    try:
        # Query all bug profiles for the given task_id that are associated with a cluster
        bug_profiles = db_session.query(BugProfile).join(
            BugClusterGroup,
            BugProfile.id == BugClusterGroup.bug_profile_id
        ).filter(
            BugProfile.task_id == task_id
        ).all()

        if bug_profiles:
            print(
                f"[*] Found {len(bug_profiles)} clustered bug profiles for task {task_id}")
            return bug_profiles
        else:
            print(f"[*] No clustered bug profiles found for task {task_id}")
            return []

    except Exception as e:
        print(
            f"[!] Error querying clustered bug profiles for task {task_id}: {e}")
        return []
    finally:
        db_session.close()


def query_for_task_clusters(task_id: str, database_url: str = None) -> List[BugCluster]:
    """
    Query the database for all unique bug clusters associated with a specific task ID.

    Args:
        task_id: The ID of the task to query clusters for
        database_url: Optional database URL (if not provided, uses the global one)

    Returns:
        A list of unique BugCluster objects associated with the task
    """
    db_session = connect_database(database_url)

    try:
        # Query all unique bug clusters for the given task_id
        bug_clusters = db_session.query(BugCluster).filter(
            BugCluster.task_id == task_id
        ).all()

        if bug_clusters:
            print(
                f"[*] Found {len(bug_clusters)} bug clusters for task {task_id}")
            return bug_clusters
        else:
            print(f"[*] No bug clusters found for task {task_id}")
            return []

    except Exception as e:
        print(f"[!] Error querying bug clusters for task {task_id}: {e}")
        return []
    finally:
        db_session.close()


def query_for_cluster_profiles(cluster_id: int, database_url: str = None) -> List[BugProfile]:
    """
    Query the database for all bug profiles in a specific cluster.

    Args:
        cluster_id: The ID of the cluster to query profiles for
        database_url: Optional database URL (if not provided, uses the global one)

    Returns:
        A list of BugProfile objects in the cluster
    """
    db_session = connect_database(database_url)

    try:
        # Get all bug profiles in this cluster
        profiles = db_session.query(BugProfile).join(
            BugClusterGroup,
            BugProfile.id == BugClusterGroup.bug_profile_id
        ).filter(
            BugClusterGroup.bug_cluster_id == cluster_id
        ).all()

        print(
            f"[*] Found {len(profiles)} bug profiles in cluster {cluster_id}")
        return profiles

    except Exception as e:
        print(f"[!] Error querying profiles in cluster {cluster_id}: {e}")
        return []
    finally:
        db_session.close()


def query_for_smallest_profile_id(bug_cluster_id: int, database_url: str = None) -> int:
    """
    Query the database for the smallest bug_profile_id associated with a specific bug cluster.

    Args:
        bug_cluster_id: The ID of the bug cluster to query
        database_url: Optional database URL (if not provided, uses the global one)

    Returns:
        The smallest bug_profile_id in the cluster, or None if no profiles found
    """
    db_session = connect_database(database_url)

    try:
        # Query for the minimum bug_profile_id in the given cluster
        smallest_profile_id = db_session.query(
            func.min(BugClusterGroup.bug_profile_id)
        ).filter(
            BugClusterGroup.bug_cluster_id == bug_cluster_id
        ).scalar()

        if smallest_profile_id:
            print(
                f"[*] Found smallest bug_profile_id {smallest_profile_id} for cluster {bug_cluster_id}")
            return smallest_profile_id
        else:
            print(f"[*] No bug profiles found for cluster {bug_cluster_id}")
            return None

    except Exception as e:
        print(
            f"[!] Error querying smallest profile ID for cluster {bug_cluster_id}: {e}")
        return None
    finally:
        db_session.close()


def query_for_cluster_id(bug_profile_id: int, database_url: str = None) -> int:
    """
    Query the database for the bug_cluster_id associated with a specific bug profile.

    Args:
        bug_profile_id: The ID of the bug profile to query
        database_url: Optional database URL (if not provided, uses the global one)

    Returns:
        The bug_cluster_id associated with the profile, or None if not found
    """
    db_session = connect_database(database_url)

    try:
        # Query for the bug_cluster_id associated with the given bug_profile_id
        cluster_id = db_session.query(
            BugClusterGroup.bug_cluster_id
        ).filter(
            BugClusterGroup.bug_profile_id == bug_profile_id
        ).first()

        if cluster_id:
            print(
                f"[*] Found bug_cluster_id {cluster_id[0]} for profile {bug_profile_id}")
            return cluster_id[0]  # Extract the ID from the result tuple
        else:
            print(f"[*] No cluster found for bug profile {bug_profile_id}")
            return None

    except Exception as e:
        print(
            f"[!] Error querying cluster ID for profile {bug_profile_id}: {e}")
        return None
    finally:
        db_session.close()


def add_new_cluster_to_db(bug_profile_id: int, database_url: str = None):
    """
    Add a new bug cluster to the database for a given bug profile ID.

    Args:
        bug_profile_id: The ID of the bug profile to create a cluster for
        database_url: Optional database URL (if not provided, uses the global one)

    Returns:
        The ID of the newly created bug cluster
    """
    db_session = connect_database(database_url)

    try:
        # First, get the bug profile to access its task_id, trigger_point, and summary
        bug_profile = db_session.query(BugProfile).filter(
            BugProfile.id == bug_profile_id
        ).first()

        if not bug_profile:
            print(f"[!] No bug profile found with ID {bug_profile_id}")
            return None

        # Create a new bug cluster with the same task_id, trigger_point, and summary
        new_cluster = BugCluster(
            task_id=bug_profile.task_id,
            trigger_point=bug_profile.trigger_point
        )

        db_session.add(new_cluster)
        db_session.flush()  # Flush to get the new cluster ID

        # Create a new bug cluster group linking the bug profile to the new cluster
        new_cluster_group = BugClusterGroup(
            bug_profile_id=bug_profile_id,
            bug_cluster_id=new_cluster.id
        )

        db_session.add(new_cluster_group)
        db_session.commit()

        print(
            f"[+] Created new bug cluster {new_cluster.id} for bug profile {bug_profile_id}")
        return new_cluster.id

    except Exception as e:
        db_session.rollback()
        print(
            f"[!] Error creating bug cluster for profile {bug_profile_id}: {e}")
        raise
    finally:
        db_session.close()


def associate_profile_to_cluster(new_bug_profile_id: int, existing_bug_profile, database_url: str = None):
    """
    Associate a bug profile with an existing bug cluster.

    Args:
        new_bug_profile_id: The ID of the bug profile to associate with a cluster
        existing_bug_profile: The existing bug profile object that is already associated with a cluster
        database_url: Optional database URL (if not provided, uses the global one)

    Returns:
        True if association was successful, False otherwise
    """
    db_session = connect_database(database_url)

    try:
        # Find the bug cluster associated with the existing bug profile
        existing_cluster_group = db_session.query(BugClusterGroup).filter(
            BugClusterGroup.bug_profile_id == existing_bug_profile.id
        ).first()

        if not existing_cluster_group:
            print(
                f"[!] No cluster found for bug profile {existing_bug_profile.id}")
            return None

        # Check if the new bug profile is already associated with this cluster
        existing_association = db_session.query(BugClusterGroup).filter(
            BugClusterGroup.bug_profile_id == new_bug_profile_id,
            BugClusterGroup.bug_cluster_id == existing_cluster_group.bug_cluster_id
        ).first()

        if existing_association:
            print(
                f"[*] Bug profile {new_bug_profile_id} is already associated with cluster {existing_cluster_group.bug_cluster_id}")
            return existing_cluster_group.bug_cluster_id

        # Create a new association between the new bug profile and the existing cluster
        new_cluster_group = BugClusterGroup(
            bug_profile_id=new_bug_profile_id,
            bug_cluster_id=existing_cluster_group.bug_cluster_id
        )

        db_session.add(new_cluster_group)
        db_session.commit()

        print(
            f"[+] Associated bug profile {new_bug_profile_id} with existing cluster {existing_cluster_group.bug_cluster_id}")
        return existing_cluster_group.bug_cluster_id

    except Exception as e:
        db_session.rollback()
        print(
            f"[!] Error associating bug profile {new_bug_profile_id} with cluster: {e}")
        raise
    finally:
        db_session.close()
