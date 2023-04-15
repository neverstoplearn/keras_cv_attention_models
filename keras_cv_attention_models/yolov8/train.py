import copy
import math
import torch
import numpy as np
from tqdm import tqdm
from pathlib import Path
from torch import nn
from torch.cuda import amp
from torch.optim import lr_scheduler
# from ultralytics.yolo.utils.torch_utils import ModelEMA

class FakeArgs:
    def __init__(self, **kwargs):
        self.update(**kwargs)

    def update(self, **kwargs):
        for kk, vv in kwargs.items():
            setattr(self, kk, vv)

def build_optimizer(model, lr=0.01, momentum=0.937, decay=5e-4):
    g = [], [], []  # optimizer parameter groups
    bn = tuple(v for k, v in nn.__dict__.items() if 'Norm' in k)  # normalization layers, i.e. BatchNorm2d()
    for v in model.modules():
        if hasattr(v, 'bias') and isinstance(v.bias, nn.Parameter):  # bias (no decay)
            g[2].append(v.bias)
        if isinstance(v, bn):  # weight (no decay)
            g[1].append(v.weight)
        elif hasattr(v, 'weight') and isinstance(v.weight, nn.Parameter):  # weight (with decay)
            g[0].append(v.weight)

    optimizer = torch.optim.SGD(g[2], lr=lr, momentum=momentum, nesterov=True)
    optimizer.add_param_group({'params': g[0], 'weight_decay': decay})  # add g0 with weight_decay
    optimizer.add_param_group({'params': g[1], 'weight_decay': 0.0})  # add g1 (BatchNorm2d weights)
    return optimizer

def train(model, dataset_path="coco.yaml", epochs=100, batch_size=16):
    from keras_cv_attention_models.yolov8 import eval, data, losses

    if torch.cuda.is_available():
        model = model.cuda()
        use_amp = True
    else:
        model = model.cpu()
        use_amp = False

    warmup_epochs = 3
    close_mosaic = 10

    cfg = FakeArgs(data=dataset_path, imgsz=640, iou=0.7, single_cls=False, max_det=300, task='detect', mode='train', split='val', half=False)
    cfg.update(project=None, name=None, save_txt=False, conf=None, save_hybrid=False, save_json=False, plots=False, verbose=True)

    train_loader, val_loader = data.get_data_loader(dataset_path=dataset_path)
    _ = model.train()
    device = next(model.parameters()).device  # get model device
    compute_loss = losses.Loss(device=device)
    accumulate = max(round(64 / batch_size), 1)
    optimizer = build_optimizer(model)
    # lf = lambda x: (x * (1 - 0.01) / warmup_epochs + 0.01) if x < warmup_epochs else ((1 - x / epochs) * (1.0 - 0.01) + 0.01)  # linear
    lf = lambda x: (1 - x / epochs) * (1.0 - 0.01) + 0.01  # linear
    scheduler = lr_scheduler.LambdaLR(optimizer, lr_lambda=lf)
    scaler = amp.GradScaler(enabled=use_amp)
    validator = eval.Validator(val_loader=val_loader, model=model, cfg=cfg)
    # validator = v8.detect.DetectionValidator(val_loader, save_dir=Path("./test"), args=copy.copy(cfg))
    # ema = ModelEMA(model)

    nb = len(train_loader)
    nbs = 64
    nw = max(round(warmup_epochs * nb), 100)
    warmup_bias_lr = 0.1
    momentum = 0.937
    warmup_momentum = 0.8
    last_opt_step = -1
    for epoch in range(0, epochs):
        # self.run_callbacks('on_train_epoch_start')
        model.train()
        # Update attributes (optional)
        if epoch == (epochs - close_mosaic):
            print('Closing dataloader mosaic')
            if hasattr(train_loader.dataset, 'mosaic'):
                train_loader.dataset.mosaic = False
            if hasattr(train_loader.dataset, 'close_mosaic'):
                train_loader.dataset.close_mosaic(hyp=cfg)

        tloss = None
        optimizer.zero_grad()
        loss_names = ["box_loss", "cls_loss", "dfl_loss"]
        print(('\n' + '%11s' * (3 + len(loss_names))) % ('Epoch', *loss_names, 'Instances', 'Size'))
        pbar = tqdm(enumerate(train_loader), total=nb, bar_format='{l_bar}{bar:10}{r_bar}')
        for i, batch in pbar:
            # self.run_callbacks('on_train_batch_start')
            ni = i + nb * epoch
            if ni <= nw:
                xi = [0, nw]  # x interp
                accumulate = max(1, np.interp(ni, xi, [1, nbs / batch_size]).round())
                for j, x in enumerate(optimizer.param_groups):
                    # bias lr falls from 0.1 to lr0, all other lrs rise from 0.0 to lr0
                    x['lr'] = np.interp(
                        ni, xi, [warmup_bias_lr if j == 0 else 0.0, x['initial_lr'] * lf(epoch)])
                    if 'momentum' in x:
                        x['momentum'] = np.interp(ni, xi, [warmup_momentum, momentum])

            # Forward
            with torch.cuda.amp.autocast(use_amp):
                preds = model(batch['img'].to(device, non_blocking=True).float() / 255)
                loss, loss_items = compute_loss(preds, batch)
                tloss = (tloss * i + loss_items) / (i + 1) if tloss is not None else loss_items

            # Backward
            scaler.scale(loss).backward()

            # Optimize - https://pytorch.org/docs/master/notes/amp_examples.html
            if ni - last_opt_step >= accumulate:
                # optimizer_step(model, optimizer, scaler)
                scaler.unscale_(optimizer)  # unscale gradients
                torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=10.0)  # clip gradients
                scaler.step(optimizer)
                scaler.update()
                optimizer.zero_grad()
                # ema.update(model)
                last_opt_step = ni

            loss_len = tloss.shape[0] if len(tloss.size()) else 1
            losses = tloss if loss_len > 1 else torch.unsqueeze(tloss, 0)
            pbar.set_description(
                ('%11s' * 1 + '%11.4g' * (2 + loss_len)) %
                (f'{epoch + 1}/{epochs}', *losses, batch['cls'].shape[0], batch['img'].shape[-1]))
        scheduler.step()
        validator()

if __name__ == "__main__":
    sys.path.append('../ultralytics/')
    # from ultralytics import YOLO
    from keras_cv_attention_models.yolov8 import train, yolov8, torch_wrapper

    # model = YOLO('../ultralytics/ultralytics/models/v8/yolov8n.yaml').model
    model = yolov8.YOLOV8_N(input_shape=(3, None, None), classifier_activation=None, pretrained=None)
    model = torch_wrapper.Detect(model)
    train.train(model, dataset_path="coco128.yaml")