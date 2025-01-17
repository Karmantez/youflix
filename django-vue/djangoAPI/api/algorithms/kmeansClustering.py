from rest_framework import status
from rest_framework.decorators import api_view

from django.http import JsonResponse
from django.db.models import Max 

from api.models import User, Profile, UserCluster

from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

import pandas as pd
import numpy as np

import json
import os
import sys

BASE_DIR = os.path.dirname(
            os.path.dirname(
                    os.path.dirname(
                            os.path.abspath(__file__)
                    )
            )
        )

url = os.path.join(BASE_DIR, 'data', 'mapper')
latent_user = np.load(os.path.join(url, 'latent_user.npy'))
user_mapper = open(os.path.join(url, 'userMapper.json')).read()
# mapper / KEY:userid, value: index
user_mapper = json.loads(user_mapper)


@api_view(['GET'])
def C_Cluster(request):
    # collaborative filtering을 위한 학습된 유저에 한해 주기적으로 할 예정
    # kmeans 클러스터링
    kmeans = KMeans(n_clusters=7).fit(latent_user)

    df = pd.DataFrame(latent_user)
    df['cluster'] = kmeans.labels_
    print(df)

    for userid, df_index in user_mapper.items():
        print(userid)
        try:
            profile = Profile.objects.get(id=userid)
            cluster = df.loc[df_index]['cluster']
            profile.kmeans_cluster = cluster
            profile.save()
            UserCluster(user_id=userid, kmeans_cluster=cluster).save()
        except Profile.DoesNotExist:
            cluster = df.loc[df_index]['cluster']
            UserCluster(user_id=userid, kmeans_cluster=cluster).save()

    return JsonResponse({'status': status.HTTP_200_OK})


# 벡터사이 유클리드 거리 구하는 함수
def dist_raw(v1, v2):
    # 정규화
    v1_normalized = v1/np.linalg.norm(v1)
    v2_normalized = v2/np.linalg.norm(v2)
    delta = v1_normalized - v2_normalized
    return np.linalg.norm(delta)


def U_Cluster():
    profiles = Profile.objects.all()
    df = pd.DataFrame(list(profiles.values()))
    df = df.set_index("user_id")
    # admin 제거 및 불필요한 열 삭제
    numeric_df = df[df.occupation != 'admin'].drop(['id', 'username'], axis=1)
    # 군집별 centroid값 구하기 위한 범주형 변수 수치화
    numeric_df.loc[df['gender'] == 'M', 'gender'] = 1
    numeric_df.loc[df['gender'] == 'male', 'gender'] = 1
    numeric_df.loc[df['gender'] == 'F', 'gender'] = 2
    numeric_df.loc[df['gender'] == 'female', 'gender'] = 2
    numeric_df.loc[df['gender'] == 'other', 'gender'] = 3
    occupation_map = {
        0: "other", 1: "academic/educator", 2: "artist", 3: "clerical/admin", 4: "college/grad student",
        5: "customer service", 6: "doctor/health care", 7: "executive/managerial", 8: "farmer", 9: "homemaker",
        10: "K-12 student", 11: "lawyer", 12: "programmer", 13: "retired", 14: "sales/marketing",
        15: "scientist", 16:  "self-employed", 17: "technician/engineer", 18: "tradesman/craftsman",
        19: "unemployed", 20: "writer"
    }
    for k, v in occupation_map.items():
        numeric_df.loc[df['occupation'] == v, 'occupation'] = k

    # 표준화
    # new_df : 성별, 나이, 직업 열만 추출
    new_df = numeric_df.drop(['movie_taste', 'kmeans_cluster'], axis=1)
    std_scaler = StandardScaler()
    fitted = std_scaler.fit(new_df)
    std_vec = std_scaler.transform(new_df)
    std_df = pd.DataFrame(std_vec, columns=new_df.columns, index=list(new_df.index.values))
    std_df['kmeans_cluster'] = numeric_df['kmeans_cluster']

    # 군집별 centroid
    mean_df = std_df.groupby(['kmeans_cluster']).mean()
    cluter_mean_vec = mean_df.to_numpy()

    # 새로 들어온 유저 대상 비슷한 군집에 할당
    max_id_object = UserCluster.objects.aggregate(user_id=Max('user_id'))
    max_id = max_id_object['user_id']

    # std_df['user_id'] = numeric_df['user_id']
    target_users = std_df[std_df.index > max_id].loc[:, ['gender', 'age', 'occupation']]
    new_cluster_list = []
    for i, new_user in enumerate(target_users.to_numpy()):
        min_dist = sys.maxsize
        min_cluster_i = None
        for c_i, cluster_vec in enumerate(cluter_mean_vec):
            d = dist_raw(cluster_vec, new_user)
            if d < min_dist:
                min_dist = d
                min_cluster_i = c_i
        new_cluster_list.append(min_cluster_i)
    target_users['cluster'] = new_cluster_list

    return target_users
