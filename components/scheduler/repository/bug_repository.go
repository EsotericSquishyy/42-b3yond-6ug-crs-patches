package repository

import (
	"crs-scheduler/models"
	"database/sql"

	"gorm.io/gorm"
)

type BugRepository interface {
	GetMaxBugID() (int64, error)
	GetNewBugs(lastID int64) ([]models.Bug, error)
	GetMaxBugGroupsID() (int64, error)
	GetNewBugProfileIDsInBugGroups(lastID int64) ([]int64, int64, error)
}

type BugRepositoryImpl struct {
	db *gorm.DB
}

func NewBugRepository(db *gorm.DB) BugRepository {
	return &BugRepositoryImpl{db: db}
}

// get the maximum id of the bugs table. If the table is empty, return 0.
func (r *BugRepositoryImpl) GetMaxBugID() (int64, error) {
	var maxID sql.NullInt64
	result := r.db.Model(&models.Bug{}).
		Select("MAX(id)").
		Scan(&maxID)
	if result.Error != nil {
		return 0, result.Error
	}
	if !maxID.Valid {
		return 0, nil
	}

	return maxID.Int64, nil
}

// get new bugs (task is processing and bug id is greater than the last id)
func (r *BugRepositoryImpl) GetNewBugs(lastID int64) ([]models.Bug, error) {
	var bugs []models.Bug
	result := r.db.Joins("JOIN tasks ON bugs.task_id = tasks.id").
		Where("tasks.status = ? AND bugs.id > ?",
			"processing", lastID).
		Order("bugs.id ASC").
		Find(&bugs)
	if result.Error != nil {
		return nil, result.Error
	}
	return bugs, nil
}

// check the bug groups table for new records, and return unique bug profiles id
func (r *BugRepositoryImpl) GetNewBugProfileIDsInBugGroups(lastID int64) ([]int64, int64, error) {
	var bugGroups []struct {
		BugProfileID int64
		ID           int64
	}
	result := r.db.Model(&models.BugGroup{}).
		Select("bug_profile_id, id").
		Distinct().
		Where("id > ?", lastID).
		Find(&bugGroups)
	if result.Error != nil {
		return nil, 0, result.Error
	}

	var bugProfileIDs []int64
	maxID := lastID
	for _, bg := range bugGroups {
		bugProfileIDs = append(bugProfileIDs, bg.BugProfileID)
		if bg.ID > maxID {
			maxID = bg.ID
		}
	}
	return bugProfileIDs, maxID, nil
}

// get the maximum id of the bug groups table. If the table is empty, return 0.
func (r *BugRepositoryImpl) GetMaxBugGroupsID() (int64, error) {
	var maxID sql.NullInt64
	result := r.db.Model(&models.BugGroup{}).
		Select("MAX(id)").
		Scan(&maxID)
	if result.Error != nil {
		return 0, result.Error
	}
	if !maxID.Valid {
		return 0, nil
	}
	return maxID.Int64, nil
}
