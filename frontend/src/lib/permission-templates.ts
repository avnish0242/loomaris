export type AppType = 'static' | 'container' | 'lambda';

const STATIC_ACTIONS = [
  's3:CreateBucket', 's3:DeleteBucket', 's3:PutBucketPolicy', 's3:GetBucketPolicy',
  's3:PutPublicAccessBlock', 's3:GetBucketPublicAccessBlock', 's3:ListBucket',
  's3:PutObject', 's3:GetObject', 's3:DeleteObject', 's3:PutBucketWebsite',
  'cloudfront:CreateDistribution', 'cloudfront:UpdateDistribution',
  'cloudfront:GetDistribution', 'cloudfront:DeleteDistribution',
  'cloudfront:CreateOriginAccessControl', 'cloudfront:GetOriginAccessControl',
  'cloudfront:DeleteOriginAccessControl', 'cloudfront:TagResource',
  'cloudfront:CreateInvalidation',
];

const CONTAINER_EXTRA_ACTIONS = [
  'ecr:GetAuthorizationToken', 'ecr:BatchCheckLayerAvailability', 'ecr:GetDownloadUrlForLayer',
  'ecr:BatchGetImage', 'ecr:InitiateLayerUpload', 'ecr:UploadLayerPart',
  'ecr:CompleteLayerUpload', 'ecr:PutImage', 'ecr:CreateRepository',
  'ecr:DescribeRepositories', 'ecr:DeleteRepository', 'ecr:SetRepositoryPolicy',
  'ecs:CreateCluster', 'ecs:DeleteCluster', 'ecs:RegisterTaskDefinition',
  'ecs:DeregisterTaskDefinition', 'ecs:CreateService', 'ecs:UpdateService',
  'ecs:DeleteService', 'ecs:DescribeServices', 'ecs:DescribeClusters',
  'ecs:DescribeTaskDefinition', 'ecs:RunTask', 'ecs:StopTask', 'ecs:ListTasks',
  'iam:PassRole',
  'elasticloadbalancing:CreateLoadBalancer', 'elasticloadbalancing:DeleteLoadBalancer',
  'elasticloadbalancing:CreateTargetGroup', 'elasticloadbalancing:DeleteTargetGroup',
  'elasticloadbalancing:CreateListener', 'elasticloadbalancing:DeleteListener',
  'elasticloadbalancing:ModifyTargetGroup', 'elasticloadbalancing:RegisterTargets',
  'elasticloadbalancing:DeregisterTargets', 'elasticloadbalancing:DescribeLoadBalancers',
  'elasticloadbalancing:DescribeTargetGroups', 'elasticloadbalancing:DescribeListeners',
  'ec2:DescribeVpcs', 'ec2:DescribeSubnets', 'ec2:DescribeSecurityGroups',
  'ec2:DescribeAvailabilityZones', 'ec2:CreateSecurityGroup', 'ec2:DeleteSecurityGroup',
  'ec2:AuthorizeSecurityGroupIngress', 'ec2:RevokeSecurityGroupIngress',
  'logs:CreateLogGroup', 'logs:DeleteLogGroup', 'logs:PutRetentionPolicy',
  'logs:CreateLogStream', 'logs:PutLogEvents', 'logs:DescribeLogGroups',
];

const LAMBDA_ACTIONS = [
  'lambda:CreateFunction', 'lambda:UpdateFunctionCode', 'lambda:UpdateFunctionConfiguration',
  'lambda:DeleteFunction', 'lambda:GetFunction', 'lambda:ListFunctions',
  'lambda:AddPermission', 'lambda:RemovePermission', 'lambda:InvokeFunction',
  'lambda:PublishVersion', 'lambda:CreateAlias', 'lambda:UpdateAlias',
  'apigateway:POST', 'apigateway:PUT', 'apigateway:GET', 'apigateway:DELETE',
  'apigateway:PATCH',
  'iam:PassRole',
  'logs:CreateLogGroup', 'logs:DeleteLogGroup', 'logs:PutRetentionPolicy',
  'logs:CreateLogStream', 'logs:PutLogEvents', 'logs:DescribeLogGroups',
];

export function getPermissionPolicy(appType: AppType): object {
  let actions: string[];
  let sid: string;

  if (appType === 'container') {
    actions = [...STATIC_ACTIONS, ...CONTAINER_EXTRA_ACTIONS];
    sid = 'LoomarisContainerDeploy';
  } else if (appType === 'lambda') {
    actions = LAMBDA_ACTIONS;
    sid = 'LoomarisLambdaDeploy';
  } else {
    actions = STATIC_ACTIONS;
    sid = 'LoomarisStaticDeploy';
  }

  return {
    Version: '2012-10-17',
    Statement: [
      {
        Sid: sid,
        Effect: 'Allow',
        Action: Array.from(new Set(actions)).sort(),
        Resource: '*',
      },
    ],
  };
}

export function getTrustPolicy(deployerArn: string, externalId: string): object {
  return {
    Version: '2012-10-17',
    Statement: [
      {
        Effect: 'Allow',
        Principal: { AWS: deployerArn },
        Action: 'sts:AssumeRole',
        Condition: { StringEquals: { 'sts:ExternalId': externalId } },
      },
    ],
  };
}

export function getRequiredActionsForType(appType: AppType): string[] {
  if (appType === 'container') return Array.from(new Set(STATIC_ACTIONS.concat(CONTAINER_EXTRA_ACTIONS))).sort();
  if (appType === 'lambda') return Array.from(new Set(LAMBDA_ACTIONS)).sort();
  return Array.from(new Set(STATIC_ACTIONS)).sort();
}

export const APP_TYPE_LABELS: Record<AppType, string> = {
  static: 'Static Site (S3 + CloudFront)',
  container: 'Container App (ECS Fargate + ALB)',
  lambda: 'Serverless (Lambda + API Gateway)',
};
