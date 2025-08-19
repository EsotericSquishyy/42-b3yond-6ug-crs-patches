package services

import (
	"errors"

	"crs-gateway/internal/db"

	"gorm.io/gorm"
)

type UserService interface {
	NewUser(username string, password string) error
	VerifyUser(username string, password string) (userId int, err error)
}

type UserServiceImpl struct {
	db *gorm.DB
}

func NewUserService(db *gorm.DB) UserService {
	return &UserServiceImpl{
		db: db,
	}
}

func (s *UserServiceImpl) NewUser(username string, password string) error {
	var user db.User
	user.Username = username
	user.Password = password
	return s.db.Create(&user).Error
}

func (s *UserServiceImpl) VerifyUser(username string, password string) (userId int, err error) {
	var user db.User
	if err := s.db.Where("username = ?", username).First(&user).Error; err != nil {
		return 0, errors.New("invalid username or password")
	}

	if user.Password != password {
		return 0, errors.New("invalid username or password")
	}

	return user.ID, nil
}
