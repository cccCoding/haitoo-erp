"""直接清空所有公司的产品库相关表。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import delete

from app.database import SessionLocal
from app.models import (
    ProductLibraryDailySnapshot, ProductLibraryDailySnapshotItem,
    ProductLibraryOrder, ProductLibraryOrderProduct, ProductLibraryOrderSkuQuantity,
    ProductLibraryProduct, ProductLibraryRankingTask, ProductLibrarySnapshotOrderProduct,
    ProductLibrarySource,
)


TABLES = (
    ProductLibraryOrderSkuQuantity,
    ProductLibrarySnapshotOrderProduct,
    ProductLibraryDailySnapshotItem,
    ProductLibraryOrderProduct,
    ProductLibraryRankingTask,
    ProductLibraryDailySnapshot,
    ProductLibraryOrder,
    ProductLibraryProduct,
    ProductLibrarySource,
)


def main():
    with SessionLocal.begin() as db:
        for model in TABLES:
            db.execute(delete(model))
    print("产品库相关 9 张表已全部清空")


if __name__ == "__main__":
    main()
