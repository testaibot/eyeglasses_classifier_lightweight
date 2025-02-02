import torch
import torchvision
import numpy as np
import argparse
import time
from sklearn.metrics import f1_score
from torchvision import transforms, utils
from typing import Tuple
from image_folder import ImageFolderWithPaths, SingleImageFolder
from train import NORMALIZITAION_FOR_PRETRAINED
import os


def parse_args():
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description='Inference script'
    )
    parser.add_argument('--images-path', type=str, help='Path to images', required=True)
    parser.add_argument('--model-params-path', type=str, help='Model parameters path', dest='model_params', required=True)
    parser.add_argument('--model-kind', type=str, help='Model kind "squeeze" or "resnet"', dest='model_kind', default='squeeze')


    args = parser.parse_args()
    return args 


if __name__ == '__main__':
    args = parse_args()
    print(args)
    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    print("Device", device)
    
    print('creating model')
    model = torchvision.models.squeezenet1_1(pretrained=False, num_classes=1)

    if args.model_params is not None: 
        model.load_state_dict(torch.load(args.model_params, map_location=device))
        model.to(device)
        model.eval()
        print("Model parameters are loaded.")
        
    transform = transforms.Compose([
        transforms.CenterCrop(400), #later use bbox from yolov5n
        transforms.Resize(224),
        transforms.ToTensor(),
        NORMALIZITAION_FOR_PRETRAINED
    ]) # this transformation adopted for specific test cases, maybe you will need your own one
    images = SingleImageFolder(args.images_path, transform=transform)
    

    t_accum = 0
    counter = 0
    
    os.mkdir(os.path.join(args.images_path, "1"))
    os.mkdir(os.path.join(args.images_path, "0"))
    
    for img_tensor, path in images:
        t_start = time.time()
        has_glasses = model(img_tensor.to(device).unsqueeze(0))  # Pr(has glasses | face_image)
        t_accum += time.time() - t_start
		
        if (has_glasses > 5): 
            outpath = os.path.join(args.images_path, "1", os.path.basename(path))
            print(outpath)
            os.rename(path, outpath)
        elif(has_glasses < 0.1):
            outpath = os.path.join(args.images_path, "0", os.path.basename(path))
            print(outpath)
            os.rename(path, outpath)
        else: pass

        counter += 1
    

    print(f'Total time: {round(t_accum, 3)} sec; average time on image: {round(t_accum / counter , 3)} sec')

        
    
