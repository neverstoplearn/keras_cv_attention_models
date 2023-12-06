# ___Keras Segment Anything___
***

## Summary
  - Paper [PDF 2304.02643 Segment Anything](https://arxiv.org/abs/2304.02643)
  - Paper [PDF 2306.14289 FASTER SEGMENT ANYTHING: TOWARDS LIGHTWEIGHT SAM FOR MOBILE APPLICATIONS](https://arxiv.org/pdf/2306.14289.pdf)
  - [Github facebookresearch/segment-anything](https://github.com/facebookresearch/segment-anything)
  - [Github ChaoningZhang/MobileSAM](https://github.com/ChaoningZhang/MobileSAM)
  - MobileSAM weights ported from [Github ChaoningZhang/MobileSAM](https://github.com/ChaoningZhang/MobileSAM)
  - EfficientViT_SAM weights ported from [Github mit-han-lab/efficientvit](https://github.com/mit-han-lab/efficientvit)
## Models
  | Model               | Params | FLOPs | Input | COCO val mIoU | Download |
  | ------------------- | ------ | ----- | ----- | ------------- | -------- |
  | MobileSAM           | 5.75M  | 39.4G | 1024  | 72.8          | [multiple mobile_sam_5m_*](https://github.com/leondgarse/keras_cv_attention_models/releases/tag/segment_anything)  |
  | EfficientViT_SAM_L0 | 30.73M | 35.4G | 512   | 74.45         | [multiple efficientvit_sam_l0_*](https://github.com/leondgarse/keras_cv_attention_models/releases/tag/segment_anything)  |
## Usage
  - **Basic [Mask and bbox input still not tested]**
    ```py
    from keras_cv_attention_models import segment_anything, test_images
    mm = segment_anything.MobileSAM()
    image = test_images.dog_cat()
    points, labels = np.array([[400, 256]]), np.array([1])
    masks, iou_predictions, low_res_masks = mm(image, points, labels)
    fig = mm.show(image, masks, iou_predictions, points=points, labels=labels, save_path='aa.jpg')
    ```
    ![sam_mobile_sam_5m](https://github.com/leondgarse/keras_cv_attention_models/assets/5744524/b4d5dbc7-69d9-47b1-936b-64bd00e7ec3e)
  - **Call args**
    - **points**: combinging with `labels`, specific points coordinates as background or foreground. np.array value in shape `[None, 2]`, `2` means `[left, top]`. left / top value range in `[0, 1]` or `[0, width]` / `[0, height]`.
    - **labels**: combinging with `points`, specific points coordinates as background or foreground. np.array value in shape `[None]`, value in `[0, 1]`, where 0 means relative point being background, and 1 foreground.
    - **boxes**: specific box area performing segmentation. np.array value in shape `[None, 4]`, `4` means `[left, top, right, bottom]`. left and right / top and bottom value range in `[0, 1]` or `[0, width]` / `[0, height]`.
    - **masks**: NOT tested.
  - **Using PyTorch backend** by set `KECAM_BACKEND='torch'` environment variable.
    ```py
    os.environ['KECAM_BACKEND'] = 'torch'
    import torch
    from keras_cv_attention_models import segment_anything, test_images
    # >>>> Using PyTorch backend
    mm = segment_anything.EfficientViT_SAM_L0()
    image = test_images.dog_cat()
    points, labels = [[0.5, 0.8], [0.5, 0.2], [0.8, 0.8]], [1, 1, 0]
    with torch.no_grad():
        masks, iou_predictions, low_res_masks = mm(image, points, labels)
    fig = mm.show(image, masks, iou_predictions, points=points, labels=labels, save_path='bb.jpg')
    ```
    ![sam_efficientvit_l0](https://github.com/leondgarse/keras_cv_attention_models/assets/5744524/72135535-1bfe-4ab0-abe6-980ce50c8045)
## Verification with PyTorch version
  ```py
  """ PyTorch MobileSAM """
  sys.path.append("../pytorch-image-models/")
  sys.path.append('../MobileSAM/')
  from mobile_sam import sam_model_registry, SamAutomaticMaskGenerator, SamPredictor

  mobile_sam = sam_model_registry["vit_t"](checkpoint="../MobileSAM/weights/mobile_sam.pt")
  _ = mobile_sam.eval()
  predictor = SamPredictor(mobile_sam)

  from PIL import Image
  from keras_cv_attention_models import test_images
  # Resize ahead, as torch one using BILINEAR, and kecam using BICUBIC
  image = np.array(Image.fromarray(test_images.dog_cat()).resize([1024, 1024], resample=Image.Resampling.BILINEAR))
  point_coords, point_labels = np.array([(400, 400)]), np.array([1])
  predictor.set_image(image)
  torch_out = predictor.predict(point_coords=point_coords, point_labels=point_labels, multimask_output=True)

  """ Kecam MobileSAM """
  from keras_cv_attention_models import segment_anything
  mm = segment_anything.MobileSAM()
  masks, iou_predictions, low_res_masks = mm(image, point_coords, point_labels)

  """ Verification """
  print(f"{np.allclose(torch_out[0], masks[1:, :, :]) = }")
  # np.allclose(torch_out[0], masks[1:, :, :]) = True
  print(f"{torch_out[1] = }")
  # torch_out[1] = array([0.8689907 , 0.7555798 , 0.99140215], dtype=float32)
  print(f"{iou_predictions[1:] = }")
  # iou_predictions[1:] = array([0.868991  , 0.7555795 , 0.99140203], dtype=float32)
  print(f"{np.allclose(torch_out[2], low_res_masks[1:, :, :], atol=1e-4) = }")
  # np.allclose(torch_out[2], low_res_masks[1:, :, :], atol=1e-4) = True
  ```
  **EfficientViT-L0-SAM**
  ```py
  """ PyTorch EfficientViT-L0-SAM """
  sys.path.append("../pytorch-image-models/")
  sys.path.append('../efficientvit/')
  import torch
  from efficientvit.sam_model_zoo import create_sam_model
  from efficientvit.models.efficientvit.sam import EfficientViTSamPredictor
  tt = create_sam_model('l0', weight_url='EfficientViT-L0-SAM.pt')
  _ = tt.eval()
  efficientvit_sam_predictor = EfficientViTSamPredictor(tt)

  os.environ['KECAM_BACKEND'] = 'torch'  # TF bicubic resize if different from Torch, allclose atol could be rather high
  from keras_cv_attention_models import test_images
  point_coords, point_labels = np.array([(256, 256)]), np.array([1])

  image = test_images.dog_cat()
  efficientvit_sam_predictor.set_image(image)
  torch_out = efficientvit_sam_predictor.predict(point_coords=point_coords, point_labels=point_labels, multimask_output=True)

  """ Kecam EfficientViT_SAM_L0 with PyTorch backend """
  from keras_cv_attention_models import segment_anything
  # >>>> Using PyTorch backend
  mm = segment_anything.EfficientViT_SAM_L0()
  with torch.no_grad():
      masks, iou_predictions, low_res_masks = mm(image, point_coords, point_labels)

  """ Verification """
  same_masks = (torch_out[0] == masks[1:, :, :]).sum() / np.prod(torch_out[0].shape)
  print("same masks percentage: {:.6f}%".format(same_masks * 100))
  # same masks percentage: 99.999619%
  print(f"{torch_out[1] = }")
  # torch_out[1] = array([0.6856826 , 0.998912  , 0.96785474], dtype=float32)
  print(f"{iou_predictions[1:] = }")
  # iou_predictions[1:] = array([0.68567175, 0.99891114, 0.96785533], dtype=float32)
  print(f"{np.allclose(torch_out[2], low_res_masks[1:, :, :], atol=1e-3) = }")
  # np.allclose(torch_out[2], low_res_masks[1:, :, :], atol=1e-3) = True
  ```