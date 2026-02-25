"""
Gold image distribution logic.
Shared between API poller (push completion) and admin redistribute action.
"""
import logging
from datetime import datetime
from flask import current_app
from app.extensions import db
from app.models import Node, GoldImage, GoldImageNode
from app.tart_client import TartAPIError

logger = logging.getLogger(__name__)


def trigger_gold_distribution(gold_name):
    """
    Create/reset GoldImageNode records for each active node and start pull_image on each.
    Called after gold push completes or when admin clicks Re-Distribute.
    """
    gold = GoldImage.query.filter_by(name=gold_name).first()
    if not gold:
        logger.warning("trigger_gold_distribution: gold image %r not found", gold_name)
        return False

    nodes = Node.query.filter_by(active=True).all()
    for node in nodes:
        gn = GoldImageNode.query.filter_by(
            gold_image_id=gold.id,
            node_id=node.id,
        ).first()
        if not gn:
            gn = GoldImageNode(gold_image_id=gold.id, node_id=node.id)
            db.session.add(gn)
        gn.status = 'pending'
        gn.status_detail = None
        gn.op_key = f'gold-{gold.id}-node-{node.id}'
        gn.started_at = None
        gn.completed_at = None
        db.session.flush()

    db.session.commit()

    for node in nodes:
        gn = GoldImageNode.query.filter_by(
            gold_image_id=gold.id,
            node_id=node.id,
        ).first()
        if not gn:
            continue
        try:
            current_app.tart.pull_image(
                node,
                gold.registry_tag,
                gn.op_key,
                expected_disk_gb=gold.disk_size_gb,
            )
            gn.status = 'pulling'
            gn.started_at = datetime.utcnow()
            db.session.commit()
        except TartAPIError as e:
            logger.warning(
                "trigger_gold_distribution: pull_image failed gold=%s node=%s: %s",
                gold_name,
                node.name,
                e,
            )
            gn.status = 'failed'
            gn.status_detail = str(e)
            gn.completed_at = datetime.utcnow()
            db.session.commit()

    return True
