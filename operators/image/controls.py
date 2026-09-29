"""Controls for the image workload — design §3: the healthy control and the seven benign configuration changes.

Ground truth is workload 1's (a control: "no incident", no evidence, no admissible repair, oracle None); only the
workload family and the edits differ. Every benign type must QUALIFY on development seeds 0–29 on AMD before any
case is built (scripts/qualify_image_benign.py; STAGE4 4.0.6's test). Ids are W1-safe (no segment occurs in any
workspace file).

The declaration order is the block pairing (``benign_design(seeds, IMAGE_BENIGN_OPERATORS)``): workload 1's six
types in workload 1's order, then the seventh — the LR-schedule no-op (author, 2026-09-28): the LR-schedule fault's
SAME three keys with decay factor 1.0, so flagging the keys can be told apart from finding the unit bug.
"""
from __future__ import annotations

from operators.base import IncidentOperator
from operators.control.benign import _BenignConfigOperator
from operators.control.healthy import HealthyControlOperator
from operators.image.common import WORKLOAD_FAMILY


class ImageHealthyControlOperator(HealthyControlOperator):
    id = "control.healthy_image.v1"
    WORKLOAD_FAMILY = WORKLOAD_FAMILY


class _ImageBenign(_BenignConfigOperator):
    WORKLOAD_FAMILY = WORKLOAD_FAMILY


class ImageBenignBatchSize(_ImageBenign):
    id = "control.benign_img_bs256.v1"
    EDITS = {"optim.batch": 256}
    FORM = "changed"
    DESCRIPTION = "Routine change: mini-batch size 128 -> 256"


class ImageBenignEpochs(_ImageBenign):
    id = "control.benign_img_ep10.v1"
    EDITS = {"sched.epochs": 10}
    FORM = "changed"
    DESCRIPTION = "Routine change: train 10 epochs instead of 8"


class ImageBenignWeightDecay(_ImageBenign):
    id = "control.benign_img_wd1e3.v1"
    EDITS = {"optim.weight_decay": 0.001}
    FORM = "changed"
    DESCRIPTION = "Routine change: weight decay 5e-4 -> 1e-3"


class ImageBenignDropout(_ImageBenign):
    id = "control.benign_img_do01.v1"
    EDITS = {"net.dropout": 0.1}
    FORM = "added"
    DESCRIPTION = "Routine change: dropout 0.1 before the classifier (new key)"


class ImageBenignLearningRate(_ImageBenign):
    id = "control.benign_img_lr004.v1"
    EDITS = {"optim.base_lr": 0.04}
    FORM = "changed"
    DESCRIPTION = "Routine change: learning rate 0.05 -> 0.04 (within normal range)"


class ImageBenignGradClip(_ImageBenign):
    id = "control.benign_img_clip1.v1"
    EDITS = {"optim.grad_clip": 1.0}
    FORM = "added"
    DESCRIPTION = "Routine change: enable gradient-norm clipping at 1.0 (new key)"


class ImageBenignScheduleNoop(_ImageBenign):
    id = "control.benign_img_sched_noop.v1"
    EDITS = {"sched.decay_every": 1, "sched.decay_gamma": 1.0, "sched.interval_unit": "steps"}
    FORM = "added"
    DESCRIPTION = "Routine change: step-decay schedule keys with decay factor 1.0 (new keys; rate unchanged)"


IMAGE_BENIGN_OPERATORS = (ImageBenignBatchSize, ImageBenignEpochs, ImageBenignWeightDecay, ImageBenignDropout,
                          ImageBenignLearningRate, ImageBenignGradClip, ImageBenignScheduleNoop)

for _cls in (ImageHealthyControlOperator, *IMAGE_BENIGN_OPERATORS):
    assert isinstance(_cls(), IncidentOperator), f"{_cls.__name__} does not satisfy IncidentOperator"
