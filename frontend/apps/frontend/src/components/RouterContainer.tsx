/**
 * 此组件可用于react-router>=6.4.0的特性，比如loader等Data API
 * 见：https://reactrouter.com/en/main/routers/picking-a-router
 */
import { Spin } from 'antd';
import React, { useMemo } from 'react';
import _ from 'lodash';
import DocumentTitle from 'react-document-title';
import type { RouteObject } from 'react-router-dom';
import { createBrowserRouter, RouterProvider, useMatches } from 'react-router-dom';

import type { Match } from '@/components/Breadcrumb';

// 将对应的面包屑信息添加到页面标题中
function RouteWithTitle({ children }: { children: React.ReactNode }) {
  const matches = useMatches() as Match[];
  const title = _.chain(matches)
    .filter((match) => Boolean(match.handle?.crumb))
    .map((match) => match.handle.crumb!(match.data))
    .last()
    .value() as string;

  return (
    // TODO：默认标题可配置（环境变量 or 常量）
    <DocumentTitle title={title ? `${title} - YOLO MCP` : 'YOLO MCP'}>
      <>{children}</>
    </DocumentTitle>
  );
}

function mapRoutes(inputRoutes: RouteObject[]): RouteObject[] {
  return inputRoutes.map((route) => {
    const element = <RouteWithTitle>{route.element}</RouteWithTitle>;
    if (route.index) return { ...route, element };
    return { ...route, element, children: route.children ? mapRoutes(route.children) : undefined };
  });
}

export interface RouterProps {
  routes: RouteObject[];
  basename?: string;
}

export default function RouterContainer({ routes, basename }: RouterProps) {
  const router = useMemo(
    () =>
      createBrowserRouter(mapRoutes(routes), {
        basename,
      }),
    [basename, routes],
  );
  const fallback = <Spin style={{ width: '100vw', marginTop: '40vh' }} spinning />;

  return <RouterProvider router={router} fallbackElement={fallback} />;
}
