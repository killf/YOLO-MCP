import type { RouteObject } from 'react-router';
import { Outlet, useLocation, useNavigate } from 'react-router';
import { useEffect } from 'react';
import { i18n } from '@yolo-mcp/i18n';

import Register from '@/pages/register';
import Projects from '@/pages/projects';
import ProjectEdit from '@/pages/projects.[id].edit';
import ProjectAnnotation from '@/pages/projects.[id].samples.[id]';
import Samples from '@/pages/projects.[id]';
import ProjectSamplesFinished from '@/pages/projects.[id].samples.finished';
import Page404 from '@/pages/404';
import MainLayout from '@/layouts/MainLayoutWithNavigation';
import Users from '@/pages/users';
import Tokens from '@/pages/tokens';

import type { ProjectLoaderResult } from './loaders/project.loader';
import { projectLoader, projectsLoader } from './loaders/project.loader';
import { rootLoader } from './loaders/root.loader';
import { sampleLoader } from './loaders/sample.loader';
import RequireAuth from './components/RequireSSO';
import { registerLoader } from './loaders/register.loader';
import { loginLoader } from './loaders/login.loader';
import LoginPage from './pages/login';

function Root() {
  const location = useLocation();
  const navigate = useNavigate();

  useEffect(() => {
    // 如果是根路径，跳转到项目管理（以项目管理为首页）
    if (location.pathname === '/' || location.pathname === '') {
      navigate('/projects');
    }
  }, [location.pathname, navigate]);

  if (!window.IS_ONLINE) {
    return <Outlet />;
  }

  return (
    <RequireAuth>
      <Outlet />
    </RequireAuth>
  );
}

const routes: RouteObject[] = [
  {
    path: '/',
    id: 'root',
    element: <Root />,
    loader: rootLoader,
    children: [
      {
        element: <MainLayout />,
        children: [
          { path: 'users', element: <Users /> },
          { path: 'tokens', element: <Tokens /> },
        ],
      },
      {
        path: 'projects',
        element: <MainLayout />,
        errorElement: <Page404 />,
        id: 'projects',
        loader: projectsLoader,
        handle: {
          crumb: () => {
            return i18n.t('projectList');
          },
        },
        children: [
          {
            index: true,
            element: <Projects />,
          },
          {
            path: ':projectId',
            id: 'project',
            element: <Outlet />,
            loader: projectLoader,
            handle: {
              crumb: (data: ProjectLoaderResult) => {
                return data?.project?.name;
              },
            },
            children: [
              {
                index: true,
                element: <Samples />,
              },
              {
                path: 'edit',
                element: <ProjectEdit />,
                loader: async ({ params }) => {
                  return params.projectId !== '0' ? i18n.t('projectEdit') : i18n.t('createProject');
                },
                handle: {
                  crumb: (data: string) => {
                    return data;
                  },
                },
              },
              {
                path: 'samples',
                id: 'samples',
                element: <Outlet />,
                children: [
                  {
                    path: ':sampleId',
                    element: <ProjectAnnotation />,
                    loader: sampleLoader,
                    id: 'annotation',
                    handle: {
                      crumb: () => {
                        return i18n.t('start');
                      },
                    },
                  },
                  {
                    path: 'finished',
                    element: <ProjectSamplesFinished />,
                    loader: projectLoader,
                    handle: {
                      crumb: () => {
                        return i18n.t('finished');
                      },
                    },
                  },
                ],
              },
            ],
          },
        ],
      },
    ],
  },
  {
    path: 'login',
    loader: loginLoader,
    element: <LoginPage />,
  },
  {
    path: 'register',
    loader: registerLoader,
    element: <Register />,
    handle: {
      crumb: () => {
        return i18n.t('signUp');
      },
    },
  },
  {
    path: '*',
    element: <Page404 />,
  },
];

export default routes;
