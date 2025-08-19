package db

import (
	"go.uber.org/fx"
	"gorm.io/driver/postgres"
	"gorm.io/gorm"
)

type Params struct {
	fx.In

	DatabaseURL string `name:"database_url"`
}

func NewDBConnection(p Params) (*gorm.DB, error) {
	return gorm.Open(postgres.Open(p.DatabaseURL), &gorm.Config{})
}
