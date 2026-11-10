import Icon, { PoweroffOutlined } from '@ant-design/icons';
import { FlexLayout } from '@yolo-mcp/components-react';
import { Button, Divider, Dropdown, Popover, Tag } from 'antd';
import { Link, useMatch, useNavigate } from 'react-router-dom';
import { useTranslation } from '@yolo-mcp/i18n';

import { ReactComponent as LocalDeploy } from '@/assets/svg/local-deploy.svg';
import { ReactComponent as ToolboxSvg } from '@/assets/svg/toolbox.svg';
import { goAuth } from '@/utils/sso';
import useMe from '@/hooks/useMe';
import queryClient from '@/api/queryClient';

import AppPanel from '../AppPanel';
import Breadcrumb from '../Breadcrumb';
import { YoloMcpLogo, NavigationWrapper } from './style';
import ProjectTip from './ProjectTip';
import LanguageSwitcher from '../LangSwitcher';
import { UserAvatar } from '../UserAvatar';

const Homepage = () => {
  const me = useMe();
  const navigate = useNavigate();
  const isSampleDetail = useMatch('/projects/:projectId/samples/:sampleId');
  const { t } = useTranslation();

  const logout = async (e: any) => {
    e.stopPropagation();
    e.nativeEvent.stopPropagation();
    e.preventDefault();

    localStorage.removeItem('token');
    queryClient.clear();

    if (window.IS_ONLINE) {
      await goAuth();
    } else {
      navigate('/login');
    }
  };

  return (
    <NavigationWrapper className="navigation" items="center" justify="space-between" padding="0 1.5rem">
      <FlexLayout.Item flex items="center" gap={window.IS_ONLINE ? '.5rem' : '3rem'}>
        <Link to="/">
          <FlexLayout.Item flex items="center">
            <YoloMcpLogo />

            {window.IS_ONLINE && (
              <Tag bordered={false} color="var(--color-fill-secondary)" style={{ color: 'var(--color-text)' }}>
                Beta
              </Tag>
            )}
          </FlexLayout.Item>
        </Link>
        {window.IS_ONLINE && <Divider type="vertical" />}
        <Breadcrumb hideHome={window.IS_ONLINE} />
      </FlexLayout.Item>
      <FlexLayout.Item flex gap="1rem">
        <ProjectTip visible={Boolean(isSampleDetail)} />
        {window.IS_ONLINE && (
          <Popover title={null} content={<AppPanel />}>
            <Button
              type="link"
              icon={<ToolboxSvg />}
              style={{ color: 'rgba(0, 0, 0, 0.85)', display: 'flex', alignItems: 'center' }}
            >
              {t('openSourceToolbox')}
            </Button>
          </Popover>
        )}
        {window.IS_ONLINE && (
          <a data-wiz="local-deploy-top-right" href="https://github.com/killf/LabelS#readme">
            <Button type="link" style={{ color: 'rgba(0, 0, 0, 0.85)' }} icon={<Icon component={LocalDeploy} />}>
              {t('localDeploy')}
            </Button>
          </a>
        )}
        <LanguageSwitcher />
        <Dropdown
          trigger={['click']}
          menu={{
            items: [
              { key: 'tokens', label: <Link to="/tokens">访问令牌 / MCP</Link> },
              ...(me.data?.is_admin ? [{ key: 'users', label: <Link to="/users">用户管理</Link> }] : []),
              {
                label: (
                  <FlexLayout.Item onClick={logout} flex gap=".5rem" padding=".25rem 0">
                    <PoweroffOutlined />
                    <span>{t('logout')}</span>
                  </FlexLayout.Item>
                ),
                key: 'logout',
                title: t('logout'),
              },
            ],
          }}
        >
          <UserAvatar
            user={me?.data}
            shortName={false}
            showTooltip={false}
            placement="bottomRight"
            style={{ backgroundColor: 'var(--color-primary)', color: '#fff' }}
          />
        </Dropdown>
      </FlexLayout.Item>
    </NavigationWrapper>
  );
};
export default Homepage;
